"""Capture and compare computed-style snapshots of the Weaver sub-site.

The Weaver sub-site is being migrated from the Tailwind Play CDN to the
repository's compiled Tailwind v4 and daisyUI v5 pipeline. The migration is
meant to be behaviour-preserving, so each step is judged by diffing a fresh
snapshot against a baseline taken before any edit. See
``docs/execplans/weaver-daisy-migration.md``.

Three subcommands, each safe to re-run:

    uv run python scripts/weaver_snapshot.py capture .weaver-baseline
    uv run python scripts/weaver_snapshot.py shots .weaver-baseline-shots
    uv run python scripts/weaver_snapshot.py diff .weaver-baseline .weaver-after

``capture`` records computed styles via ``css-view`` and is the objective
gate; ``diff`` exits non-zero when any page changed. ``shots`` records
full-page screenshots via ``agent-browser`` for human review, because some
regressions — a wrong icon glyph, a texture that failed to load — are obvious
to the eye and invisible in a style diff.

All three read the published tree under ``public/``, so run ``bun run build``
first. Each serves that tree itself on a local port and stops the server
afterwards, including on failure.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import difflib
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import typing as typ
import urllib.error
import urllib.request
from pathlib import Path

import cyclopts

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
HTTP_SERVER = REPO_ROOT / "node_modules" / ".bin" / "http-server"

# 360 exercises the mobile drawer, 768 the tablet breakpoint, and 1440 the
# fixed-sidebar layout the site was designed against.
SCREENSHOT_WIDTHS = (360, 768, 1440)

# The walker mode's node budget. The largest Weaver page is well under this;
# the ceiling only guards against a runaway capture.
MAX_NODES = 8000

# How long a browser-driving subprocess may take before the run is called off.
# A headless browser that never returns would otherwise hang the snapshot
# indefinitely. Matches the timeout the css-view and Playwright probes in
# tests/ already use for the same tools.
TOOL_TIMEOUT_SECONDS = 90

# How long to wait for another run to finish starting its server. A healthy
# start takes under a second, so anything near this means the holder was
# killed mid-start rather than that it is merely slow.
LOCK_TIMEOUT_SECONDS = 30

app = cyclopts.App(
    name="weaver-snapshot",
    help="Capture and compare Weaver computed-style snapshots.",
)


def _page_paths(root: Path = PUBLIC_WEAVER) -> list[str]:
    """List the published Weaver pages as base-relative URL paths.

    Derived from the published tree rather than hard-coded, so a page added to
    ``config/pages.yaml`` is captured without editing this script.

    Parameters
    ----------
    root
        The published sub-site to walk. Passed in so the traversal — and its
        failure — can be exercised against a directory a test controls.

    Returns
    -------
    list of str
        Paths relative to ``/weaver/``, such as ``""`` for the home page and
        ``"commands/act/"`` for a nested one, in sorted order.

    Raises
    ------
    SystemExit
        If the root is absent, or if any part of the tree beneath it cannot be
        read.
    """
    if not root.is_dir():
        message = f"{root} is missing; run 'bun run build' first"
        raise SystemExit(message)

    def refuse(error: OSError) -> typ.NoReturn:
        """Turn a failure to read part of the tree into a refusal to capture."""
        message = (
            f"{error.filename} under {root} could not be read ({error}), so the "
            f"page list would be short by however much is beneath it. A capture "
            f"missing a page compares clean against a baseline that has it."
        )
        raise SystemExit(message)

    # `rglob` swallows an OSError on a descendant and yields nothing further
    # beneath it, so an unreadable directory would silently shorten the list
    # rather than stop the run. `os.walk` will report it if asked to.
    pages = [
        f"{Path(directory).relative_to(root).as_posix()}/".removeprefix("./")
        for directory, _subdirs, files in os.walk(root, onerror=refuse)
        if "index.html" in files
    ]
    return sorted(pages)


def _slug(page: str) -> str:
    """Turn a page path into a filename stem.

    The mapping has to be injective, because two pages sharing a stem would
    have one capture silently overwrite the other and the diff would then
    compare a page against itself. The pages come from the published tree, so
    a directory named with an underscore is an ordinary thing to find there,
    and a naive ``"/" -> "__"`` is not injective over such names: ``a/b`` and
    ``a__b`` both flatten to ``a__b``.

    So ``_`` introduces an escape and the character after it says which:
    ``__`` is a separator and ``_u`` is a literal underscore. Reading the stem
    left to right recovers the path unambiguously, which is what makes the
    collision impossible rather than merely unlikely. The home page's stem is
    ``__home`` for the same reason — a bare ``home`` would collide with a page
    at ``home/``, and no path can produce a leading ``__`` because the leading
    separator is stripped first.

    Parameters
    ----------
    page
        A path relative to ``/weaver/``, such as ``"commands/act/"``.

    Returns
    -------
    str
        A flat, filesystem-safe stem: ``"__home"`` for the home page and
        ``"commands__act"`` for the example above.
    """
    return page.strip("/").replace("_", "_u").replace("/", "__") or "__home"


def _lock_path(port: int) -> Path:
    """Name the lock file guarding one port's startup.

    It sits in the system temp directory rather than in the repository,
    because the runs that contend are typically in different worktrees. The
    port is what they share, so the port is what the name is keyed on — and
    the user id too, since a shared ``/tmp`` is sticky and another user's file
    could not be opened for writing. Two users racing for one port are left to
    the bind probe, which catches them whoever owns the lock file.

    Parameters
    ----------
    port
        TCP port the lock guards.

    Returns
    -------
    Path
        The lock file's path. It is created on demand and left behind; the
        lock is the ``flock`` on it, not the file's existence.
    """
    return Path(tempfile.gettempdir()) / f"weaver-snapshot-{os.getuid()}-{port}.lock"


@contextlib.contextmanager
def _startup_lock(port: int) -> cabc.Iterator[None]:
    """Hold an exclusive lock on a port's startup for the duration.

    Probing a port and then spawning a server on it is check-then-act: two
    runs can both find the port free, both spawn, and one then answer the
    other's readiness poll. The loser would snapshot the winner's ``public/``
    and report the diff as its own work.

    The default port is ephemeral, so two runs normally have nothing to
    contend over; this covers the case where a port was named explicitly, and
    two runs in two worktrees were given the same number.

    Serializing probe and spawn behind one lock removes the interleaving
    rather than narrowing it: the second run reaches the probe only once the
    first is already serving, and is then refused with the ordinary
    port-in-use message rather than racing. The lock is released as soon as
    the server answers, so it covers startup and not the capture, which takes
    minutes.

    ``flock`` is advisory and POSIX-only, which suits both facts here: the
    only processes that need to co-operate are other runs of this script, and
    the repository's tooling is POSIX throughout. It is keyed on the user id
    as well as the port, because a shared ``/tmp`` is sticky and another
    user's lock file could not be opened for writing. That deliberately leaves
    two *users* unserialized, which is what :func:`_confirm_ownership` is for:
    a lock cannot prove whose server answered, and a marker can.

    Parameters
    ----------
    port
        TCP port whose startup is being serialized.

    Yields
    ------
    None
        With the lock held.

    Raises
    ------
    SystemExit
        If the lock is still held after :data:`LOCK_TIMEOUT_SECONDS`,
        which means another run has been starting for far longer than a
        healthy start takes.
    """
    with _exclusive(_lock_path(port), f"the startup lock for port {port}"):
        yield


@contextlib.contextmanager
def _lock_file(path: Path) -> cabc.Iterator[typ.IO[bytes]]:
    """Open a lock file in a shared temp directory without trusting it.

    The lock's path is predictable — it has to be, since two runs find each
    other by computing the same name — and the system temp directory is
    writable by everyone. So the file at that path may not be the one this
    process expects: another user can create it first, or leave a symlink
    there pointing at something of ours. Opening it with ``open("w")`` would
    follow that link and truncate whatever it found.

    ``O_NOFOLLOW`` refuses a symlink outright, ``O_CREAT`` without ``O_TRUNC``
    leaves an existing file's contents alone, and the mode denies everyone but
    the owner. What is opened is then checked to be a regular file this user
    owns, because winning the race is not the same as being handed the right
    file.

    Parameters
    ----------
    path
        The lock file to open, creating it if absent.

    Yields
    ------
    IO
        The open file, for :func:`fcntl.flock`. Nothing is written to it; the
        lock is the ``flock``, not the contents.

    Raises
    ------
    SystemExit
        If the path is a symlink, is not a regular file, belongs to another
        user, or cannot be opened.
    """
    try:
        descriptor = os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
        )
    except OSError as exc:
        message = (
            f"the lock file {path} could not be opened ({exc}). If it is a "
            f"symlink or belongs to another user, remove it; nothing but this "
            f"script should be writing there."
        )
        raise SystemExit(message) from exc

    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            message = f"the lock file {path} is not a regular file; remove it"
            raise SystemExit(message)
        if status.st_uid != os.getuid():
            message = (
                f"the lock file {path} belongs to uid {status.st_uid} rather "
                f"than this user; remove it, or pass --port to use another"
            )
            raise SystemExit(message)
        with os.fdopen(descriptor, "rb+") as handle:
            descriptor = -1
            yield handle
    finally:
        if descriptor != -1:
            os.close(descriptor)


@contextlib.contextmanager
def _exclusive(path: Path, contended: str) -> cabc.Iterator[None]:
    """Hold an exclusive advisory lock on ``path`` for the duration.

    Parameters
    ----------
    path
        The lock file. Created on demand and left behind; the lock is the
        ``flock`` on it, not the file's existence.
    contended
        What is being locked, for the message a waiting run eventually gives up
        with.

    Yields
    ------
    None
        With the lock held.

    Raises
    ------
    SystemExit
        If the lock is still held after :data:`LOCK_TIMEOUT_SECONDS`.
    """
    with _lock_file(path) as handle:
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    message = (
                        f"another run has held {contended} ({path}) for over "
                        f"{LOCK_TIMEOUT_SECONDS}s; it may have been killed "
                        f"partway. Remove the lock file if no run is active."
                    )
                    raise SystemExit(message) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _output_lock_path(out_dir: Path) -> Path:
    """Name the lock file guarding one output directory's publication.

    Keyed on the resolved path, so two runs writing the same directory contend
    however they spelled it, and two writing different directories do not.

    Parameters
    ----------
    out_dir
        The directory the run will publish into.

    Returns
    -------
    Path
        The lock file's path.
    """
    digest = hashlib.sha256(str(out_dir).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"weaver-snapshot-{os.getuid()}-{digest}.lock"


type Mover = cabc.Callable[[Path, Path], object]


def _publish(
    staging: Path, destination: Path, suffix: str, move: Mover = Path.replace
) -> None:
    """Move a finished capture into place, or leave the destination as it was.

    Deleting the previous run's files and then moving this run's in is not
    failure-atomic: a rename that fails partway leaves the destination holding
    some of each, with the originals already gone. That is the worst state to
    be in, because it still looks like a directory of snapshots.

    So the previous files are moved aside rather than deleted, and put back if
    anything goes wrong. Every step is a rename within one filesystem, which
    is atomic per file, and the rollback is the same operation in reverse.
    Only the extension being written is touched, so a ``capture`` and a
    ``shots`` run can share a directory.

    Parameters
    ----------
    staging
        The directory this run captured into.
    destination
        Where the results belong.
    suffix
        File extension being published, including the leading dot.
    move
        How to move one file onto another, atomically. Injected so a failure
        partway through can be provoked without a full disk.

    Raises
    ------
    OSError
        If publication fails, after the destination has been put back as it
        was. The caller turns this into a ``SystemExit`` naming the directory.
    """
    aside = staging / "replaced"
    aside.mkdir(exist_ok=True)

    rescued: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for stale in sorted(destination.glob(f"*{suffix}")):
            moved = aside / stale.name
            move(stale, moved)
            rescued.append((moved, stale))
        for captured in sorted(staging.glob(f"*{suffix}")):
            landed = destination / captured.name
            move(captured, landed)
            published.append(landed)
    except OSError:
        # Undo this run's half-publication first, so putting the previous
        # files back cannot be blocked by a file this run had just landed.
        for landed in published:
            with contextlib.suppress(OSError):
                landed.unlink()
        for moved, original in rescued:
            with contextlib.suppress(OSError):
                move(moved, original)
        raise


@contextlib.contextmanager
def _staged(out_dir: Path, suffix: str) -> cabc.Iterator[Path]:
    """Capture into a private directory, and publish it only if everything worked.

    Writing straight into ``out_dir`` gives a run no exclusive claim on it. Two
    runs sharing one would interleave: the second clears the directory the
    first is still filling, and the pages captured before that point are gone
    while the ones after remain, so the result looks like a complete capture of
    a site half of whose pages were never visited. A run that fails partway
    leaves the same thing behind.

    So each run captures into a directory of its own and publishes at the end,
    under a lock keyed on the destination. Publication replaces file by file
    with :func:`os.replace`, which is atomic per file, and the lock makes the
    sequence of replacements atomic against another run of this script.

    Parameters
    ----------
    out_dir
        Where the results should end up.
    suffix
        File extension being written, including the leading dot.

    Yields
    ------
    Path
        The staging directory to write into.

    Raises
    ------
    SystemExit
        If the staging directory cannot be made, or publication fails.
    """
    destination = _ensure_output_dir(out_dir)
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
        )
    except OSError as exc:
        message = f"a staging directory beside {destination} could not be made ({exc})"
        raise SystemExit(message) from exc

    try:
        yield staging
    except BaseException:
        # A half-finished capture is worse than none: it would be compared as
        # though it were whole.
        shutil.rmtree(staging, ignore_errors=True)
        raise

    try:
        with _exclusive(_output_lock_path(destination), f"the output {destination}"):
            _publish(staging, destination, suffix)
    except OSError as exc:
        message = f"{destination} could not be published to ({exc})"
        raise SystemExit(message) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _refuse_occupied_port(port: int) -> None:
    """Exit rather than serve on a port somebody else already holds.

    ``http-server`` exits 1 when it cannot bind, but the readiness poll would
    then connect to the *pre-existing* server and take it for the one just
    spawned. Probing first makes that deterministic for a foreign server;
    :func:`_startup_lock` makes it deterministic for another run of this
    script, which the probe alone cannot do.

    Parameters
    ----------
    port
        TCP port to test.

    Raises
    ------
    SystemExit
        If the port cannot be bound.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # `http-server` sets SO_REUSEADDR, so it will bind a port left in
        # TIME_WAIT by the previous run. Without it here the probe is stricter
        # than the thing it is standing in for, and a capture refuses to start
        # for a minute after the last one on a port nothing is actually using.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            message = (
                f"port {port} is already in use, so the snapshot would capture "
                f"whatever is being served there rather than this worktree's "
                f"public/ ({exc}). Stop that server, or pass --port."
            )
            raise SystemExit(message) from exc


class _Pollable(typ.Protocol):
    """The one thing waiting on a server needs from the process running it.

    Annotating the parameter as ``subprocess.Popen[bytes]`` overstated it: the
    wait asks whether the child is still running and nothing else. Narrowing
    the contract to that is what lets it be checked against a stand-in that
    reports a chosen sequence of exits, rather than against a real process
    whose timing a test cannot control.
    """

    def poll(self) -> int | None:
        """Return the exit status, or ``None`` while the process runs."""
        ...  # pragma: no cover - a protocol has no body


def _await_server(server: _Pollable, base: str, port: int) -> None:
    """Wait until the spawned server answers, and confirm it is the one that did.

    Parameters
    ----------
    server
        The freshly spawned ``http-server`` process, or anything that reports
        whether it is still running.
    base
        The origin it should be listening on.
    port
        The port, for the messages.

    Raises
    ------
    SystemExit
        If the child exits while starting, if it does not answer within
        roughly ten seconds, or if it is no longer running once something on
        its port has answered — in which case the answer came from something
        else, and this run must not snapshot it.
    """
    # Poll rather than sleeping a fixed interval, so a slow start does not
    # silently yield a directory full of failed captures.
    for _ in range(50):
        # A server that has already exited will never answer, and anything
        # that does answer on its port is not it.
        if (status := server.poll()) is not None:
            message = (
                f"http-server exited with status {status} while starting on "
                f"port {port}; it may have lost a race to bind it"
            )
            raise SystemExit(message)
        try:
            with urllib.request.urlopen(f"{base}/weaver/", timeout=1):  # noqa: S310 - literal loopback URL
                break
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    else:
        message = f"http-server did not come up on port {port}"
        raise SystemExit(message)

    # The request succeeded, but that alone does not say who answered it. If
    # the child has exited by now, something else on the port did, and the
    # capture would silently be of that.
    if (status := server.poll()) is not None:
        message = (
            f"port {port} answered, but this run's http-server had already "
            f"exited with status {status}; the reply came from another server"
        )
        raise SystemExit(message)


def _stop(server: subprocess.Popen[bytes]) -> None:
    """Stop a served process, escalating if it will not stand down.

    Parameters
    ----------
    server
        The process to stop.
    """
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # A server that will not stand down still holds the port, and the
        # next run's bind probe would refuse to start because of it.
        server.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=10)


def _server_argv(port: int) -> list[str]:
    """Build the command that serves ``public/`` on one port.

    ``-a 127.0.0.1`` is the part worth stating outright. ``http-server``
    defaults its address to ``0.0.0.0``, so without it the published tree —
    an unreleased sub-site, mid-migration — is offered to every host that can
    reach this machine, for as long as a capture runs. Nothing in this script
    needs that: every request it makes is to loopback.

    Parameters
    ----------
    port
        TCP port to listen on.

    Returns
    -------
    list of str
        The full argv, fixed apart from the port.
    """
    return [
        str(HTTP_SERVER),
        "public",
        "-a",
        "127.0.0.1",
        "-p",
        str(port),
        "-c-1",
        "--silent",
    ]


# How a port is obtained when none was named. Injected rather than called
# directly so the decision about *which* port to serve on can be exercised
# without binding one, and so the one function that touches the network stays
# at the edge where the command composes its dependencies.
type PortAllocator = cabc.Callable[[], int]


def _allocate_port() -> int:
    """Ask the kernel for a loopback port nothing is listening on.

    This is the environmental half, and the only part of port selection that
    can fail for reasons outside this process.

    Returns
    -------
    int
        A port that was free a moment ago. The bind probe and the startup lock
        in :func:`_start_server` handle the gap between then and now.

    Raises
    ------
    SystemExit
        If a port cannot be obtained at all, which means the machine has no
        ephemeral ports left or loopback is unavailable.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])
    except OSError as exc:
        message = (
            f"no loopback port could be obtained ({exc}); pass --port to name "
            f"one explicitly"
        )
        raise SystemExit(message) from exc


def _resolve_port(port: int, allocate: PortAllocator = _allocate_port) -> int:
    """Turn a requested port into the one to serve on.

    Zero means "whatever the kernel has spare", which is the default and the
    reason two concurrent runs normally have nothing to contend over at all.
    A fixed port is honoured as given, since reaching the served tree from a
    browser by hand needs a number known in advance.

    Parameters
    ----------
    port
        The requested port, or ``0``.
    allocate
        How to obtain a port when none was named. Injected so the decision can
        be tested without a socket.

    Returns
    -------
    int
        A port to serve on.
    """
    return port or allocate()


@contextlib.contextmanager
def _ownership_marker() -> cabc.Iterator[str]:
    """Put a file under ``public/`` that only this run knows the name of.

    Fetching it back is what turns "something is listening" into "the thing
    listening is serving *this* worktree's tree". Liveness of the child cannot
    establish that: an unrelated server can claim the port in the moment
    between the bind probe and the spawn, and a run in another worktree — or
    another user's, which the startup lock deliberately does not serialize —
    answers requests just as readily.

    Yields
    ------
    str
        The marker's name, relative to the served root.
    """
    name = f"weaver-snapshot-{secrets.token_hex(8)}.txt"
    marker = REPO_ROOT / "public" / name
    marker.write_text(name, encoding="utf-8")
    try:
        yield name
    finally:
        marker.unlink(missing_ok=True)


def _confirm_ownership(base: str, marker: str, port: int, when: str) -> None:
    """Check that the server on this port is serving this run's ``public/``.

    Parameters
    ----------
    base
        The origin to ask.
    marker
        The name :func:`_ownership_marker` chose, which is also its contents.
    port
        The port, for the message.
    when
        What was happening, for the message: the check runs once before the
        capture and once after, and the two failures mean different things.

    Raises
    ------
    SystemExit
        If the marker cannot be fetched or does not come back intact, in which
        case whatever is on the port is not this run's server.
    """
    try:
        with urllib.request.urlopen(f"{base}/{marker}", timeout=5) as response:  # noqa: S310 - literal loopback URL
            # Whatever is on that port is not necessarily ours, so its
            # response is not necessarily small. One byte past the marker is
            # enough to tell a match from anything longer.
            served = response.read(len(marker) + 1).decode("utf-8", "replace").strip()
    except (urllib.error.URLError, OSError) as exc:
        message = (
            f"the server on port {port} did not serve this run's marker "
            f"{when} ({exc}), so it is serving some other tree; the snapshot "
            f"would be of that. Pass --port, or leave it unset to be given a "
            f"free one."
        )
        raise SystemExit(message) from exc
    if served != marker:
        message = (
            f"port {port} returned {served!r} for this run's marker {when}; "
            f"another server has it"
        )
        raise SystemExit(message)


def _start_server(port: int, marker: str) -> subprocess.Popen[bytes]:
    """Acquire the port and return a server already answering on it, as itself.

    Parameters
    ----------
    port
        TCP port to listen on.
    marker
        The ownership marker to fetch back once it answers.

    Returns
    -------
    subprocess.Popen
        The running server. The caller owns stopping it.

    Raises
    ------
    SystemExit
        If the startup lock cannot be taken, the port is occupied, or the
        server does not come up as itself.
    """
    with _startup_lock(port):
        _refuse_occupied_port(port)
        server = subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
            _server_argv(port),
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            _await_server(server, base, port)
            _confirm_ownership(base, marker, port, "on starting")
        except BaseException:
            # Otherwise a failed start leaves a child holding the port, and
            # the next run's probe refuses to start because of it.
            _stop(server)
            raise
        return server


@contextlib.contextmanager
def _served(port: int, allocate: PortAllocator = _allocate_port) -> cabc.Iterator[str]:
    """Serve ``public/`` locally for the duration of the context.

    Parameters
    ----------
    port
        TCP port to listen on, or ``0`` to be given a free one.
    allocate
        How to obtain that free one. The default binds a loopback socket; a
        caller with its own port source can pass one instead.

    Yields
    ------
    str
        The base URL of the running server, without a trailing slash.

    Raises
    ------
    SystemExit
        If the server binary is absent, if another run holds the startup lock,
        if the port is already occupied, if the server exits while starting,
        if it does not accept connections within roughly ten seconds, or if
        the server answering on the port turns out not to be this run's —
        either when it comes up or once the capture is finished.
    """
    if not HTTP_SERVER.is_file():
        message = "node_modules/.bin/http-server is missing; run 'bun install'"
        raise SystemExit(message)

    resolved = _resolve_port(port, allocate)
    base = f"http://127.0.0.1:{resolved}"
    with _ownership_marker() as marker:
        server = _start_server(resolved, marker)
        try:
            yield base
            # Ownership is checked again on the way out, so a capture is only
            # accepted if the same server answered throughout it. Nothing
            # stops a stopped-and-replaced server from taking the port
            # mid-run, and the pages captured after that point would be its.
            _confirm_ownership(base, marker, resolved, "after the capture")
        finally:
            _stop(server)


def _ensure_output_dir(out_dir: Path) -> Path:
    """Create the output directory, without disturbing what is in it.

    Clearing belongs to publication rather than to preparation. Emptying the
    destination before a capture starts destroys the previous run's results in
    exchange for nothing, and leaves nothing behind if this run then fails
    partway — see :func:`_staged`.

    Parameters
    ----------
    out_dir
        Directory to create. Created with parents if absent.

    Returns
    -------
    Path
        The resolved absolute path to the directory.

    Raises
    ------
    SystemExit
        If the directory cannot be created.
    """
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = f"{out_dir} could not be created ({exc})"
        raise SystemExit(message) from exc
    return out_dir.resolve()


def _tool(name: str) -> str:
    """Resolve an external tool to an absolute path.

    Parameters
    ----------
    name
        The executable's name, as it appears on ``PATH``.

    Returns
    -------
    str
        The absolute path to the executable.

    Raises
    ------
    SystemExit
        If the tool is not on ``PATH``, with a message naming it.
    """
    found = shutil.which(name)
    if found is None:
        message = f"{name} is not on PATH"
        raise SystemExit(message)
    return found


# What a command needs from the outside world to drive a tool. Injecting it
# rather than calling `subprocess.run` inline is what lets the argv a command
# builds be asserted without a browser, a server, or a filesystem.
type Runner = cabc.Callable[[cabc.Sequence[str]], None]


def _run_tool(argv: cabc.Sequence[str]) -> None:
    """Run an external tool to completion, or raise.

    Parameters
    ----------
    argv
        The command to run, already resolved to an absolute executable.

    Raises
    ------
    subprocess.CalledProcessError
        If the tool exits non-zero.
    subprocess.TimeoutExpired
        If it has not finished within :data:`TOOL_TIMEOUT_SECONDS`. A headless
        browser that never returns would otherwise hang the run indefinitely.
    """
    subprocess.run(  # noqa: S603 - fixed argv built from the published tree
        list(argv),
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=TOOL_TIMEOUT_SECONDS,
    )


def _session_name() -> str:
    """Name the browser session this process should drive.

    A dedicated session keeps the run clear of any interactive browsing. It
    also has to be unique per process: ``agent-browser`` sessions are named
    globally and hold one viewport and one current page between calls, so two
    concurrent runs sharing a name would interleave — one resizing the
    viewport while the other screenshots, producing images at a width neither
    asked for and reporting success for both.

    Returns
    -------
    str
        A session name unique to this process.
    """
    return f"weaver-shots-{os.getpid()}"


def _css_view_argv(bun: str, base: str, page: str, out_dir: Path) -> list[str]:
    """Build the ``css-view`` command that snapshots one page.

    Parameters
    ----------
    bun
        Absolute path to the ``bun`` executable.
    base
        The origin the local server is listening on, without a trailing slash.
    page
        A page path relative to ``/weaver/``, as :func:`_page_paths` returns.
    out_dir
        Directory the JSON snapshot is written into.

    Returns
    -------
    list of str
        The full argv. The browser is pinned rather than left to css-view's
        default, so a change to that default cannot swap the engine — and the
        rendering — out from under a comparison.
    """
    return [
        bun,
        "x",
        "css-view",
        "--mode",
        "walker",
        "--browser",
        "chromium",
        "--max-nodes",
        str(MAX_NODES),
        "--wait-until",
        "networkidle",
        "--output",
        str(out_dir / f"{_slug(page)}.json"),
        f"{base}/weaver/{page}",
    ]


def _screenshot_argv(path: Path) -> list[str]:
    """Build the ``agent-browser`` arguments that capture one full-page image.

    Parameters
    ----------
    path
        Absolute path to write the PNG to.

    Returns
    -------
    list of str
        The subcommand and its arguments, without the executable or session.
        The path is positional and must precede the flags: passing ``--full``
        first makes agent-browser read the path as a selector and write the
        image elsewhere, reporting success either way. agent-browser also runs
        as a daemon with its own working directory, so the path must be
        absolute.
    """
    return ["screenshot", str(path), "--full"]


def _capture_pages(
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    bun: str,
    run: Runner,
) -> None:
    """Snapshot each page in turn, reporting progress as it goes.

    Parameters
    ----------
    pages
        Page paths relative to ``/weaver/``.
    out_dir
        Directory to write one JSON snapshot per page into.
    base
        The origin the local server is listening on.
    bun
        Absolute path to the ``bun`` executable.
    run
        How to run a tool. Injected so a test can assert the argv without
        launching a browser.
    """
    for page in pages:
        run(_css_view_argv(bun, base, page, out_dir))
        print(f"  {_slug(page)}")


def _shoot_pages(
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    browser: str,
    run: Runner,
) -> None:
    """Screenshot each page at each width, closing the session afterwards.

    The session is closed in a ``finally`` so an interrupted run does not
    strand a browser daemon holding the viewport it last set.

    Parameters
    ----------
    pages
        Page paths relative to ``/weaver/``.
    out_dir
        Directory to write the PNG files into.
    base
        The origin the local server is listening on.
    browser
        Absolute path to the ``agent-browser`` executable.
    run
        How to run a tool. Injected so a test can assert the argv without
        launching a browser.
    """
    session = ["--session", _session_name()]

    def drive(*args: str) -> None:
        run([browser, *args, *session])

    try:
        for width in SCREENSHOT_WIDTHS:
            drive("set", "viewport", str(width), "900")
            for page in pages:
                drive("open", f"{base}/weaver/{page}")
                drive(*_screenshot_argv(out_dir / f"{_slug(page)}@{width}.png"))
            print(f"  {width}px done")
    finally:
        with contextlib.suppress(
            subprocess.CalledProcessError, subprocess.TimeoutExpired
        ):
            drive("close")


@app.command
def capture(out_dir: Path, /, *, port: int = 0) -> None:
    """Record a computed-style snapshot of every Weaver page.

    Parameters
    ----------
    out_dir
        Directory to write one JSON snapshot per page into. Existing snapshots
        are replaced.
    port
        Port to serve ``public/`` on. The default of ``0`` asks the kernel for
        a free one, so two runs in two worktrees do not contend at all; pass a
        number only to reach the served tree from a browser by hand.
    """
    pages = _page_paths()
    bun = _tool("bun")
    print(f"capturing {len(pages)} Weaver pages into {out_dir}")

    with _staged(out_dir, ".json") as staging, _served(port) as base:
        _capture_pages(pages, staging, base, bun, _run_tool)

    print(f"done: {out_dir.resolve()}")


@app.command
def shots(out_dir: Path, /, *, port: int = 0) -> None:
    """Record full-page screenshots of every Weaver page at three widths.

    Parameters
    ----------
    out_dir
        Directory to write PNG files into. Existing images are replaced.
    port
        Port to serve ``public/`` on. The default of ``0`` asks the kernel for
        a free one, so two runs in two worktrees do not contend at all; pass a
        number only to reach the served tree from a browser by hand.
    """
    browser = _tool("agent-browser")
    pages = _page_paths()
    widths = " ".join(str(width) for width in SCREENSHOT_WIDTHS)
    print(f"screenshotting {len(pages)} Weaver pages at {widths} into {out_dir}")

    with _staged(out_dir, ".png") as staging, _served(port) as base:
        _shoot_pages(pages, staging, base, browser, _run_tool)

    print(f"done: {out_dir.resolve()}")


# The sRGB transfer function's linear-segment cutoff, from the sRGB
# specification. Named so the conversion below does not read as a magic
# number.
SRGB_LINEAR_CUTOFF = 0.0031308

# Every colour notation handled here takes three components before the
# optional alpha.
COLOUR_COMPONENTS = 3


def _srgb_channel(value: float) -> int:
    """Convert one linear-light channel to an 8-bit sRGB value.

    Parameters
    ----------
    value
        A linear-light channel, nominally in ``[0, 1]`` but allowed to fall
        outside it for colours beyond the sRGB gamut.

    Returns
    -------
    int
        The gamma-encoded channel, clamped to ``[0, 255]``.
    """
    encoded = (
        12.92 * value
        if value <= SRGB_LINEAR_CUTOFF
        else 1.055 * (abs(value) ** (1 / 2.4)) - 0.055
    )
    return max(0, min(255, round(encoded * 255)))


def _oklab_to_rgb(lightness: float, a: float, b: float) -> tuple[int, int, int]:
    """Convert an Oklab colour to 8-bit sRGB.

    Parameters
    ----------
    lightness
        The Oklab ``L`` component, nominally in ``[0, 1]``.
    a, b
        The Oklab opponent components.

    Returns
    -------
    tuple of int
        Red, green, and blue, each in ``[0, 255]``.
    """
    long_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _srgb_channel(
            4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short
        ),
        _srgb_channel(
            -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short
        ),
        _srgb_channel(
            -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short
        ),
    )


# Matches the colour notations Chromium reports in computed values. Tailwind
# v3 resolved an opacity modifier to `rgba(...)`; v4 resolves it through
# `color-mix()` in Oklab and reports `oklab(...)`. The colours are the same to
# within a rounding step, but the strings share not one character.
_COLOUR_FUNCTION = re.compile(
    r"\b(rgba?|oklab|oklch)\(\s*([^)]*)\)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?%?")


def _canonical_colour(match: re.Match[str]) -> str:
    """Rewrite one colour function as a canonical 8-bit ``rgba()`` string.

    Parameters
    ----------
    match
        A match of :data:`_COLOUR_FUNCTION`.

    Returns
    -------
    str
        ``rgba(r, g, b, a)`` with integer channels and alpha to three decimal
        places, or the original text if the arguments cannot be read.
    """
    name = match.group(1).lower()
    numbers = _NUMBER.findall(match.group(2))
    if len(numbers) < COLOUR_COMPONENTS:
        return match.group(0)

    def value(index: int, scale: float = 1.0) -> float:
        raw = numbers[index]
        return float(raw.rstrip("%")) / 100 * scale if raw.endswith("%") else float(raw)

    alpha = value(COLOUR_COMPONENTS) if len(numbers) > COLOUR_COMPONENTS else 1.0

    if name.startswith("rgb"):
        red, green, blue = (round(value(i, 255.0)) for i in range(COLOUR_COMPONENTS))
    elif name == "oklab":
        red, green, blue = _oklab_to_rgb(value(0), value(1), value(2))
    else:  # oklch
        chroma, hue = value(1), math.radians(value(2))
        red, green, blue = _oklab_to_rgb(
            value(0), chroma * math.cos(hue), chroma * math.sin(hue)
        )

    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _canonical_value(value: str) -> str:
    """Rewrite every colour function inside one computed value.

    Values such as ``box-shadow`` embed a colour among other components, so
    the substitution is applied in place rather than to the whole string.

    Parameters
    ----------
    value
        A computed property value.

    Returns
    -------
    str
        The value with each colour function in canonical ``rgba()`` form.
    """
    return _COLOUR_FUNCTION.sub(_canonical_colour, value)


# A shadow layer that paints nothing: fully transparent, no offset, no blur,
# no spread. Tailwind composes box-shadow from several `--tw-*` variables and
# v4 uses more of them than v3 did, so the same visible shadow arrives with a
# different number of these placeholders in front of it.
_EMPTY_SHADOW = "rgba(0, 0, 0, 0.000) 0px 0px 0px 0px"

# The alpha channel of a canonicalized `rgba()`, which `_canonical_colour` has
# already normalized to three decimal places by the time this runs.
_SHADOW_ALPHA = re.compile(r"rgba\([^)]*,\s*0\.000\s*\)")


def _is_transparent_shadow(layer: str) -> bool:
    """Report whether a shadow layer paints nothing.

    Alpha decides this on its own. Matching the fully-zero placeholder by its
    exact text missed any transparent layer that carried a geometry — an
    offset, a blur, a spread — even though a shadow at alpha zero is invisible
    whatever its dimensions. Two snapshots then differed over a layer neither
    of them drew.

    Parameters
    ----------
    layer
        One comma-separated layer of a canonicalized shadow value.

    Returns
    -------
    bool
        True when the layer is fully transparent and so paints nothing.
    """
    return layer == _EMPTY_SHADOW or bool(_SHADOW_ALPHA.search(layer))


def _canonical_shadow(value: str) -> str:
    """Drop the placeholder layers from a composed ``box-shadow``.

    Parameters
    ----------
    value
        A canonicalized ``box-shadow`` value.

    Returns
    -------
    str
        The value with every layer that paints nothing removed, or ``"none"``
        if no layer survives.
    """
    # Split on top-level commas only: the layers themselves contain commas,
    # inside their rgba() colour.
    layers: list[str] = []
    buffer = ""
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            layers.append(buffer.strip())
            buffer = ""
        else:
            buffer += char
    if buffer.strip():
        layers.append(buffer.strip())

    painted = [layer for layer in layers if not _is_transparent_shadow(layer)]
    return ", ".join(painted) if painted else "none"


# The physical and logical names for each border edge, paired so a width can
# be looked up from a colour property and vice versa.
_BORDER_EDGES = (
    ("border-top", "border-block-start"),
    ("border-right", "border-inline-end"),
    ("border-bottom", "border-block-end"),
    ("border-left", "border-inline-start"),
)
_ZERO_WIDTHS = frozenset({"0px", "0", "medium"})


def _drop_invisible_border_colours(style: dict[str, typ.Any]) -> None:
    """Remove the colour of any border edge that is not drawn.

    Tailwind v3's preflight defaulted every border to ``gray-200``; v4 leaves
    it at ``currentColor``. That changes the reported colour on roughly four
    and a half thousand nodes per page, of which only forty draw a border at
    all. Reporting the rest would bury the forty.

    Parameters
    ----------
    style
        A node's computed styles, modified in place.
    """
    for physical, logical in _BORDER_EDGES:
        width = style.get(f"{physical}-width", style.get(f"{logical}-width"))
        # A missing width means the walker saw the user-agent default, which
        # is zero for every element the preflight touches.
        if width is None or width in _ZERO_WIDTHS:
            style.pop(f"{physical}-color", None)
            style.pop(f"{logical}-color", None)


# Properties that take their value from the parent in practice, but which the
# walker compares against the user-agent default instead of against the
# parent. It therefore repeats them on every node in the subtree. `color-scheme`
# is inherited by specification; the rest default to `currentColor` and so
# follow `color` wherever it goes. Set once on `:root`, any of them would
# otherwise be reported five thousand times.
_TRACKS_PARENT = frozenset(
    {
        "color-scheme",
        "outline-color",
        "caret-color",
        "column-rule-color",
        "row-rule-color",
        "text-emphasis-color",
        "-webkit-text-fill-color",
        "-webkit-text-stroke-color",
    }
)


def _canonical_style(style_diff: dict[str, typ.Any] | None) -> dict[str, typ.Any]:
    """Strip incidental variation from one node's reported styles.

    Five kinds of variation are incidental:

    - ``--tw-*`` custom properties. These are Tailwind's own plumbing, and
      which of them exist is an implementation detail of the version in use,
      not something a reader can see.
    - Colour notation. Tailwind v3 resolved `text-primary/80` to `rgba(...)`;
      v4 resolves it through `color-mix()` and Chromium reports `oklab(...)`.
      Comparing the strings would report every translucent colour on the site
      as changed and bury the handful that really did. Each colour is
      therefore converted to 8-bit sRGB before comparison, which is the
      precision a screen has anyway.
    - ``opacity`` on a node running a CSS animation. The Weaver pages carry an
      ``animate-pulse`` status dot whose opacity is sampled mid-cycle.
    - Placeholder shadow layers. v4 composes ``box-shadow`` from more slots
      than v3 did, so an unchanged shadow arrives behind a different number of
      fully transparent, zero-size layers. See :func:`_canonical_shadow`.
    - The colour of a border edge with no width. See
      :func:`_drop_invisible_border_colours`.

    Parameters
    ----------
    style_diff
        The ``styleDiff`` a walker node reported, or ``None`` when it carried
        no styles of its own.

    Returns
    -------
    dict
        A fresh mapping with those variations removed. The argument is left
        alone.
    """
    style = {
        key: _canonical_value(value) if isinstance(value, str) else value
        for key, value in (style_diff or {}).items()
        if not key.startswith("--tw-")
    }
    if style.get("animation-name", "none") != "none":
        style.pop("opacity", None)
    for key in ("box-shadow", "text-shadow"):
        if isinstance(style.get(key), str):
            style[key] = _canonical_shadow(style[key])
    _drop_invisible_border_colours(style)
    return style


def _resolve_tracked(
    style: dict[str, typ.Any],
    inherited: dict[str, typ.Any],
) -> dict[str, typ.Any]:
    """Drop the tracked properties a node merely repeats from its parent.

    The walker compares the properties in :data:`_TRACKS_PARENT` against the
    user-agent default rather than against the parent, so one declaration on
    ``:root`` is reported on every node beneath it. A node keeps such a
    property only where it genuinely departs from what it was handed, and the
    departure is what its own children are then compared against.

    Parameters
    ----------
    style
        The node's normalized styles, modified in place: any tracked property
        matching the inherited value is removed.
    inherited
        What the parent carried for those properties. Empty at the root.

    Returns
    -------
    dict
        The values to hand to this node's children, which is *inherited*
        updated with whatever this node overrode.
    """
    carried = dict(inherited)
    for key in _TRACKS_PARENT & style.keys():
        if style[key] == inherited.get(key):
            del style[key]
        else:
            carried[key] = style[key]
    return carried


# Whatever the walker put in a node's `bbox`. It is a mapping today; the type
# says "some JSON value" because the normalization deliberately does not
# require that, and a snapshot reporting it otherwise should reach the diff
# rather than be dropped on the way.
type _Bbox = dict[str, typ.Any] | list[typ.Any] | str | float | bool | None


def _rounded_bbox(bbox: _Bbox) -> _Bbox:
    """Round a bounding box's numbers, absorbing subpixel text-shaping jitter.

    Two decimal places is finer than any layout shift worth reporting and
    coarser than the noise, so a real move still shows and a re-shaped glyph
    does not.

    Parameters
    ----------
    bbox
        A walker node's ``bbox``. Anything that is not a mapping is returned
        unchanged rather than discarded: the walker owns this field's shape,
        and a snapshot that starts reporting it differently should surface in
        the diff rather than be quietly dropped here.

    Returns
    -------
    dict or list or str or float or bool or None
        A fresh mapping with each numeric value rounded, or the argument
        itself when it is not a mapping.
    """
    if not isinstance(bbox, dict):
        return bbox
    return {
        key: round(value, 2) if isinstance(value, (int, float)) else value
        for key, value in bbox.items()
    }


def _normalize(
    node: dict[str, typ.Any],
    inherited: dict[str, typ.Any] | None = None,
) -> dict[str, typ.Any]:
    """Strip incidental variation from one walker node and its descendants.

    The normalization itself lives in :func:`_canonical_style`,
    :func:`_resolve_tracked` and :func:`_rounded_bbox`; this function walks the
    tree and reassembles each node from their results.

    Parameters
    ----------
    node
        A walker-mode node, as emitted by ``css-view``.
    inherited
        The values the parent node carried for the properties in
        :data:`_TRACKS_PARENT`. Empty at the root.

    Returns
    -------
    dict
        The node with those variations removed, and its children likewise. The
        argument is left alone.
    """
    style = _canonical_style(node.get("styleDiff"))
    carried = _resolve_tracked(style, inherited or {})

    normalized = dict(node)
    normalized["styleDiff"] = style
    if "bbox" in node:
        normalized["bbox"] = _rounded_bbox(node["bbox"])
    normalized["children"] = [
        _normalize(child, carried) for child in node.get("children") or []
    ]
    return normalized


class _MalformedSnapshotError(ValueError):
    """A parsed snapshot that is not the shape ``css-view`` writes."""


def _check_node(node: typ.Any, where: str) -> None:  # noqa: ANN401 - the document is untyped upstream data
    """Check one walker node, and everything below it, is the shape assumed.

    The normalization reaches for ``.get`` on every node and ``.items`` on
    every ``styleDiff``, so anything that is not a mapping surfaces from deep
    inside the recursion as ``'str' object has no attribute 'get'`` — an
    ``AttributeError``, which the read boundary was not catching, naming
    neither the file nor the node. Walking the shape first means the failure
    can say where in the tree it is.

    Parameters
    ----------
    node
        The node to check.
    where
        A breadcrumb naming its position, such as ``payload.tree.children[2]``.

    Raises
    ------
    _MalformedSnapshotError
        If the node, its ``styleDiff``, or any descendant is not the shape the
        normalization assumes.
    """
    if not isinstance(node, cabc.Mapping):
        message = f"{where} is {type(node).__name__}, not a mapping"
        raise _MalformedSnapshotError(message)

    style = node.get("styleDiff")
    if style is not None and not isinstance(style, cabc.Mapping):
        message = (
            f"{where}.styleDiff is {type(style).__name__}, not a mapping or absent"
        )
        raise _MalformedSnapshotError(message)

    children = node.get("children")
    if children is None:
        return
    # A string is a Sequence, and iterating one yields characters rather than
    # nodes, so it has to be excluded by name.
    if isinstance(children, str) or not isinstance(children, cabc.Sequence):
        message = f"{where}.children is {type(children).__name__}, not a list or absent"
        raise _MalformedSnapshotError(message)
    for index, child in enumerate(children):
        _check_node(child, f"{where}.children[{index}]")
    # Explicit, to match the early return above: a node with no children and a
    # node whose children all check out leave this function the same way.
    return


def _rendered_tree(payload: dict[str, typ.Any]) -> str:
    """Render a parsed snapshot's tree as stable, comparable text.

    Kept free of I/O, so the normalization and its serialization can be
    exercised on a literal payload rather than a file on disk.

    Parameters
    ----------
    payload
        A parsed ``css-view`` snapshot document.

    Returns
    -------
    str
        Pretty-printed JSON with sorted keys, ready to hand to a line differ.
        The capture envelope — URL, timestamp, browser — is dropped, since it
        records when the snapshot was taken, not what the page looks like.

    Raises
    ------
    KeyError
        If the document has no ``payload.tree``. :func:`_normalized_tree`
        converts this into a ``SystemExit`` naming the file.
    TypeError
        If either level is not a mapping, for the same reason.
    _MalformedSnapshotError
        If the tree is not mappings all the way down, naming the node that is
        not. :func:`_normalized_tree` converts this the same way.
    """
    tree = payload["payload"]["tree"]
    _check_node(tree, "payload.tree")
    return json.dumps(_normalize(tree), indent=2, sort_keys=True, ensure_ascii=False)


def _normalized_tree(snapshot: Path) -> str:
    """Read a snapshot and render its tree as stable, comparable text.

    This is the I/O boundary. A snapshot directory is written by ``capture``
    but read here by path, so it can be stale, truncated by an interrupted
    run, or simply not a snapshot at all. Each of those surfaces as a
    ``SystemExit`` naming the file rather than as a traceback partway through
    a comparison, where the file at fault is the one thing not on screen.

    Parameters
    ----------
    snapshot
        Path to a ``css-view`` JSON snapshot.

    Returns
    -------
    str
        The rendering :func:`_rendered_tree` produces.

    Raises
    ------
    SystemExit
        If the file cannot be read, does not hold valid JSON, or does not have
        the shape ``css-view`` writes.
    """
    try:
        text = snapshot.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"{snapshot} could not be read ({exc})"
        raise SystemExit(message) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        message = (
            f"{snapshot} is not valid JSON ({exc}); an interrupted capture "
            f"can leave a partial file behind, so recapture it"
        )
        raise SystemExit(message) from exc
    try:
        return _rendered_tree(payload)
    except (KeyError, TypeError) as exc:
        message = (
            f"{snapshot} has no payload.tree, so it is not a css-view "
            f"snapshot ({exc!r})"
        )
        raise SystemExit(message) from exc
    except _MalformedSnapshotError as exc:
        message = (
            f"{snapshot} is not the shape css-view writes: {exc}. An "
            f"interrupted capture, or a snapshot from a different tool, would "
            f"look like this; recapture it."
        )
        raise SystemExit(message) from exc


@app.command
def diff(before: Path, after: Path, /, *, context: int = 60) -> None:
    """Compare two snapshot directories and report per-page differences.

    Parameters
    ----------
    before
        Directory holding the baseline snapshots.
    after
        Directory holding the snapshots to check.
    context
        Maximum number of diff lines to print per differing page.

    Raises
    ------
    SystemExit
        With status 1 when any page differs, so this can gate a milestone.
    """
    # Read both directories under the same lock publication takes, so a diff
    # can never observe one of them halfway through being replaced. Without
    # this the reader is the remaining hole in the ownership protocol: the
    # writer's per-file replacements are each atomic, but the sequence of them
    # is not, and a diff that started midway would compare some pages from
    # this run against some from the last and report the difference as the
    # branch's work.
    with contextlib.ExitStack() as reading:
        for directory in _reading_order(before, after):
            reading.enter_context(
                _exclusive(_output_lock_path(directory), f"{directory}")
            )
        _diff_locked(before, after, context)


def _reading_order(before: Path, after: Path) -> list[Path]:
    """Order two output directories so two readers cannot deadlock on them.

    Taking them in a consistent order — resolved, then sorted — means two runs
    reading the same pair take them the same way round rather than each
    holding what the other wants. A directory named twice is locked once.

    Parameters
    ----------
    before
        The baseline directory.
    after
        The directory being checked.

    Returns
    -------
    list of Path
        The distinct resolved directories, in a stable order.
    """
    return sorted({before.resolve(), after.resolve()})


def _diff_locked(before: Path, after: Path, context: int) -> None:
    """Compare two snapshot directories, with both already locked for reading.

    Parameters
    ----------
    before
        Directory holding the baseline snapshots.
    after
        Directory holding the snapshots to check.
    context
        Maximum number of diff lines to print per differing page.

    Raises
    ------
    SystemExit
        With status 1 when any page differs.
    """
    baseline = sorted(before.glob("*.json"))
    if not baseline:
        message = f"no snapshots in {before}"
        raise SystemExit(message)

    differing = 0
    for snapshot in baseline:
        name = snapshot.stem
        candidate = after / snapshot.name
        if not candidate.is_file():
            print(f"{name:<24} MISSING in {after}")
            differing += 1
            continue

        lines = list(
            difflib.unified_diff(
                _normalized_tree(snapshot).splitlines(),
                _normalized_tree(candidate).splitlines(),
                fromfile=str(snapshot),
                tofile=str(candidate),
                lineterm="",
            )
        )
        if not lines:
            print(f"{name:<24} no differences")
            continue

        changed = sum(1 for line in lines[2:] if line[:1] in {"+", "-"})
        print(f"{name:<24} DIFFERS ({changed} changed lines)")
        for line in lines[:context]:
            print(f"    {line}")
        differing += 1

    # A page present only in the after directory is a new page, which is as
    # much a change as an altered one.
    for candidate in sorted(after.glob("*.json")):
        if not (before / candidate.name).is_file():
            print(f"{candidate.stem:<24} NEW in {after}")
            differing += 1

    print(f"{len(baseline)} pages compared, {differing} differing.")
    if differing:
        sys.exit(1)


if __name__ == "__main__":
    app()
