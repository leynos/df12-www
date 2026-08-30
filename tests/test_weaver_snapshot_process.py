"""Starting a server, waiting for it, and stopping it again.

Every seam these use is injected — the clock, the HTTP probe, the launcher —
so none of them opens a socket, sleeps, makes a request, or starts a child.
What they check is the pacing and the escalation: how many attempts, how long
between them, and what happens when a process will not stand down.
"""

from __future__ import annotations

import collections.abc as cabc
import email.message
import io
import subprocess
import typing as typ
import urllib.error
import urllib.request

import pytest

from tests.support.weaver_harness import load

if typ.TYPE_CHECKING:
    import collections.abc as cabc

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"

# A port number for the messages these tests read back. Nothing binds it.
PORT = 8099

# The bound `_stop` puts on each of its waits.
STOP_TIMEOUT = 10

locking = load("weaver_snapshot_locking")
paths = load("weaver_snapshot_paths")
process = load("weaver_snapshot_process")
serving = load("weaver_snapshot_serving")


class _FakeClock:
    """A clock that records what it was asked to wait for and never waits."""

    def __init__(self, times: cabc.Iterator[float] | None = None) -> None:
        """Store the scripted times and start with no sleeps recorded."""
        self.slept: list[float] = []
        self._times = times

    def monotonic(self) -> float:
        """Report the next scheduled time, or a fixed one."""
        return next(self._times) if self._times is not None else 0.0

    def sleep(self, seconds: float, /) -> None:
        """Record the wait rather than taking it."""
        self.slept.append(seconds)


class _Running:
    """A child that is alive whenever it is asked."""

    def poll(self) -> int | None:
        """Report still running."""
        return None


def test_the_readiness_poll_retries_until_the_server_answers() -> None:
    """The wait is a loop over a clock, so it can be checked without waiting."""
    attempts: list[str] = []
    answers_on = 3

    def probe(url: str) -> None:
        """Refuse until the scripted attempt, recording each ask."""
        attempts.append(url)
        if len(attempts) < answers_on:
            message = "connection refused"
            raise OSError(message)

    clock = _FakeClock()
    process._await_server(_Running(), "http://127.0.0.1:9999", PORT, clock, probe)

    assert len(attempts) == answers_on, (
        f"the poll should stop at the first answer; it asked {len(attempts)} times"
    )
    assert attempts == ["http://127.0.0.1:9999/weaver/"] * answers_on, (
        f"every attempt should ask the same readiness URL; got {attempts}"
    )
    assert clock.slept == [process.READINESS_POLL_SECONDS] * (answers_on - 1), (
        f"it should wait once between attempts and not after the last; "
        f"it slept {clock.slept}"
    )


def test_a_server_that_never_answers_gives_up_after_a_bounded_wait() -> None:
    """Fifty attempts rather than forever, and the message names the port."""
    attempts: list[str] = []

    def never(url: str) -> None:
        """Refuse every time, recording each ask."""
        attempts.append(url)
        message = "connection refused"
        raise OSError(message)

    clock = _FakeClock()
    with pytest.raises(SystemExit) as caught:
        process._await_server(_Running(), "http://127.0.0.1:9999", PORT, clock, never)

    assert len(attempts) == process.READINESS_ATTEMPTS, (
        f"expected {process.READINESS_ATTEMPTS} attempts, got {len(attempts)}"
    )
    assert len(clock.slept) == process.READINESS_ATTEMPTS, (
        f"it should wait after every failed attempt; it slept {len(clock.slept)} times"
    )
    message = str(caught.value.code)
    assert str(PORT) in message, f"the message should name the port; got {message!r}"
    assert "connection_failed" in message, (
        f"the message should classify the failure; got {message!r}"
    )
    assert str(process.READINESS_ATTEMPTS) in message, (
        f"the message should say how often it asked; got {message!r}"
    )


def test_a_port_that_only_redirects_is_reported_as_such() -> None:
    """A refused redirect on every probe is a different problem from silence.

    Whatever holds the port is answering — with a ``Location`` the opener
    refuses to follow — and the operator reading the giving-up message needs
    to know that, not merely that the server "did not come up".
    """

    def redirects(url: str) -> None:
        """Answer every probe with a refused redirect, as the opener would."""
        raise urllib.error.HTTPError(
            url, 302, "redirected to elsewhere", email.message.Message(), None
        )

    with pytest.raises(SystemExit) as caught:
        process._await_server(
            _Running(), "http://127.0.0.1:9999", PORT, _FakeClock(), redirects
        )

    message = str(caught.value.code)
    assert "redirect_refused" in message, (
        f"the message should classify the redirect; got {message!r}"
    )
    assert isinstance(caught.value.__cause__, urllib.error.HTTPError), (
        "the giving-up message should chain from the last probe failure"
    )


def test_an_http_error_is_classified_by_its_status() -> None:
    """A port that answers 503 on every probe is named as exactly that."""

    def unavailable(url: str) -> None:
        """Answer every probe with a 503, as a sick server would."""
        raise urllib.error.HTTPError(
            url, 503, "service unavailable", email.message.Message(), None
        )

    with pytest.raises(SystemExit) as caught:
        process._await_server(
            _Running(), "http://127.0.0.1:9999", PORT, _FakeClock(), unavailable
        )

    message = str(caught.value.code)
    assert "http_503" in message, (
        f"the message should carry the numeric status; got {message!r}"
    )
    assert str(process.READINESS_ATTEMPTS) in message, (
        f"the message should say how often it asked; got {message!r}"
    )
    assert isinstance(caught.value.__cause__, urllib.error.HTTPError), (
        "the giving-up message should chain from the last probe failure"
    )


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (None, "timeout"),
        (OSError("connection refused"), "connection_failed"),
    ],
)
def test_the_remaining_failure_categories_are_stable(
    failure: OSError | None, category: str
) -> None:
    """The category vocabulary is fixed; these pin the non-HTTP entries."""
    assert process._probe_failure_category(failure) == category


def test_the_diagnostics_repeat_nothing_the_server_chose() -> None:
    """Whatever holds the port writes its own reasons; none reach the message.

    The redirect refusal must not carry the `Location` target, and the
    giving-up message must not carry the probe failure's text — both are
    attacker-chosen on a port this harness explicitly does not trust.
    """
    hostile = "http://attacker.example/" + "A" * 4096

    refuser = process._RefuseRedirects()
    with pytest.raises(urllib.error.HTTPError) as refused:
        refuser.redirect_request(
            urllib.request.Request("http://127.0.0.1:9999/weaver/"),
            io.BytesIO(),
            302,
            "B" * 4096,
            email.message.Message(),
            hostile,
        )
    assert hostile not in str(refused.value), (
        "the refusal repeated the attacker-chosen redirect target"
    )
    assert "B" * 64 not in str(refused.value), (
        "the refusal repeated the attacker-chosen reason phrase"
    )

    def taunts(_url: str) -> None:
        """Fail with a message the server's owner chose."""
        raise OSError("C" * 4096)

    with pytest.raises(SystemExit) as caught:
        process._await_server(
            _Running(), "http://127.0.0.1:9999", PORT, _FakeClock(), taunts
        )
    message = str(caught.value.code)
    assert "C" * 64 not in message, (
        "the giving-up message repeated the probe failure's text"
    )
    assert "connection_failed" in message, (
        f"the message should still classify the failure; got {message!r}"
    )
    # Every field in the message is fixed text or a number, so its length is
    # bounded whatever the responder does; the margin covers a five-digit
    # port and a wider retry budget without inviting free text back in.
    generous_bound = 256
    assert len(message) <= generous_bound, (
        f"the giving-up message should be bounded; got {len(message)} chars"
    )


def test_the_launcher_is_given_the_argv_the_run_would_use() -> None:
    """What a start would run, checked without starting anything."""
    launched: list[cabc.Sequence[str]] = []

    def launch(argv: cabc.Sequence[str]) -> typ.NoReturn:
        """Record the argv and stop the start right there."""
        # `NoReturn` rather than `object`: a `Launcher` promises a process,
        # and a stand-in returning less would not satisfy the alias. This one
        # never returns at all, which any return type accepts.
        launched.append(list(argv))
        message = "far enough"
        raise SystemExit(message)

    with pytest.raises(SystemExit):
        serving._start_server(PORT, "marker.txt", named=False, launch=launch)

    assert launched == [serving._server_argv(PORT)], (
        f"the launcher should be handed the pinned argv; got {launched}"
    )
    assert "-a" in launched[0], f"the argv lost its address flag: {launched[0]}"
    assert "127.0.0.1" in launched[0], (
        f"the argv should still bind loopback only; got {launched[0]}"
    )


def test_stopping_a_server_that_stands_down_does_not_kill_it() -> None:
    """`terminate` then one wait, and nothing more."""

    class _Obedient:
        def __init__(self) -> None:
            """Start with nothing recorded."""
            self.calls: list[str] = []
            self.waits: list[int | None] = []

        def terminate(self) -> None:
            """Record the request to stop."""
            self.calls.append("terminate")

        def kill(self) -> None:
            """Record the escalation."""
            self.calls.append("kill")

        def wait(self, timeout: int | None = None) -> int:
            """Record the bounded wait and stand down."""
            self.calls.append("wait")
            self.waits.append(timeout)
            return 0

    server = _Obedient()
    process._stop(server)

    assert server.calls == ["terminate", "wait"], (
        f"a server that stands down should not be killed; got {server.calls}"
    )
    assert server.waits == [STOP_TIMEOUT], (
        f"the wait should be bounded at {STOP_TIMEOUT}s; got {server.waits}"
    )


def test_a_server_that_will_not_stand_down_is_killed() -> None:
    """A child still holding the port stops the next run, so escalate."""

    class _Stubborn:
        def __init__(self) -> None:
            """Start with nothing recorded."""
            self.calls: list[str] = []
            self.waits: list[int | None] = []

        def terminate(self) -> None:
            """Record the request to stop."""
            self.calls.append("terminate")

        def kill(self) -> None:
            """Record the escalation."""
            self.calls.append("kill")

        def wait(self, timeout: int | None = None) -> int:
            """Time out on the first wait, then stand down."""
            self.calls.append("wait")
            self.waits.append(timeout)
            if len(self.waits) == 1:
                raise subprocess.TimeoutExpired("http-server", timeout or 0)
            return 0

    server = _Stubborn()
    process._stop(server)

    assert server.calls == ["terminate", "wait", "kill", "wait"], (
        f"expected terminate, wait, kill, wait; got {server.calls}"
    )
    assert server.waits == [STOP_TIMEOUT, STOP_TIMEOUT], (
        f"both waits should be bounded; got {server.waits}"
    )


def test_only_the_final_wait_may_time_out_silently() -> None:
    """A child that survives `kill` is beyond this function's help.

    Nothing useful is left to do about it, so the second timeout is
    suppressed — and only that one. The first is what triggers the kill, and
    swallowing anything else would hide a real failure.
    """

    class _Unkillable:
        def __init__(self) -> None:
            """Start with nothing recorded."""
            self.calls: list[str] = []

        def terminate(self) -> None:
            """Record the request to stop."""
            self.calls.append("terminate")

        def kill(self) -> None:
            """Record the escalation."""
            self.calls.append("kill")

        def wait(self, timeout: int | None = None) -> int:
            """Time out on every wait."""
            self.calls.append("wait")
            raise subprocess.TimeoutExpired("http-server", timeout or 0)

    server = _Unkillable()
    process._stop(server)  # must not raise

    assert server.calls == ["terminate", "wait", "kill", "wait"], (
        f"both waits should have been attempted; got {server.calls}"
    )


def test_a_server_that_died_before_answering_is_not_taken_for_the_responder() -> None:
    """Something else answered on the port, and capturing it would be wrong."""

    class _Exited:
        """A child that answered nothing because it was never alive."""

        def poll(self) -> int | None:
            """Report the exit status `_await_server` asks for."""
            return 1

    with pytest.raises(SystemExit) as caught:
        process._await_server(_Exited(), "http://127.0.0.1:8099", 8099)

    assert "8099" in str(caught.value.code), (
        f"the message should name the port; got {caught.value.code!r}"
    )


def test_a_server_that_dies_after_answering_is_not_taken_for_the_responder() -> None:
    """A reply proves something is listening, not that it is this run's server.

    The bind probe and the startup lock make this unreachable between two runs
    of this script, but nothing stops an unrelated server from claiming the
    port in the moment between the probe and the spawn. The ownership check is
    what turns that into a refusal rather than a snapshot of someone else's
    pages.
    """
    replies = iter([None, 0])

    class _DiesAfterReplying:
        """Alive when asked before the request, exited when asked after it."""

        def poll(self) -> int | None:
            """Report alive, then exited, so the reply lands in between."""
            return next(replies)

    def answers(_url: str) -> None:
        """Succeed at once, the way a foreign server on the port would."""

    with pytest.raises(SystemExit) as caught:
        process._await_server(
            _DiesAfterReplying(),
            "http://127.0.0.1:8099",
            8099,
            _FakeClock(),
            probe=answers,
        )

    message = str(caught.value.code)
    assert "another server" in message, (
        f"the message should say the reply was not this run's; got {message!r}"
    )
