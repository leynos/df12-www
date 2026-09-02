"""Fixtures shared between the site-build suites.

``built_site`` lives here rather than in one test module because several
suites need it — the Weaver and Stilyagi build tests read the published
markup, and the Weaver browser tests serve it to a real Chromium — and a full
``bun run build`` costs too much to run once per module.

``served`` and ``drive`` are here for the same reason: the two Weaver browser
suites share one server and one browser session between them, rather than
starting a pair each.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

from tests.support.weaver_browser import TOOL_TIMEOUT_SECONDS
from tests.support.weaver_harness import load

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"


@pytest.fixture(scope="session")
def built_site() -> Path:
    """Build the published tree and return the Weaver sub-site's root.

    Returns
    -------
    Path
        ``public/weaver`` after a successful build.
    """
    bun_exe = shutil.which("bun")
    if not bun_exe:  # pragma: no cover - environment guard
        message = "Unable to locate 'bun' on PATH"
        raise FileNotFoundError(message)
    subprocess.run([bun_exe, "run", "build"], cwd=REPO_ROOT, check=True)  # noqa: S603 - fixed argv, no user input
    if not PUBLIC_WEAVER.is_dir():  # pragma: no cover - defensive
        message = f"expected the Weaver sub-site at {PUBLIC_WEAVER}"
        raise FileNotFoundError(message)
    return PUBLIC_WEAVER


@pytest.fixture(scope="session")
def served(built_site: Path) -> cabc.Iterator[str]:
    """Serve the published tree and yield its origin.

    Parameters
    ----------
    built_site
        The Weaver root, which the session fixture has just built.

    Yields
    ------
    str
        The origin the tree is being served on, without a trailing slash.
    """
    paths = load("weaver_snapshot_paths")
    serving = load("weaver_snapshot_serving")

    if not paths.HTTP_SERVER.is_file():  # pragma: no cover - environment guard
        pytest.skip(f"{paths.HTTP_SERVER} is missing; run 'bun install'")
    if not built_site.is_dir():  # pragma: no cover - defensive
        message = f"expected the built sub-site at {built_site}"
        raise FileNotFoundError(message)
    # `0` asks the harness for a free port, which is the same code path the
    # commands take by default. A second allocator here would be a second
    # thing to keep correct.
    with serving._served(0) as base:
        yield base


@pytest.fixture(scope="session")
def drive() -> cabc.Iterator[cabc.Callable[..., str]]:
    """Yield a way to run ``agent-browser`` in a session of this test run's own.

    ``agent-browser`` sessions are named globally and hold one viewport and one
    current page between calls, so a shared name would let a concurrent run
    resize the viewport out from under a page these tests had just opened.

    Yields
    ------
    callable
        Takes the subcommand and its arguments; returns stdout.
    """
    # `or pytest.skip(...)` rather than an `if`, because the skip's `NoReturn`
    # is what narrows this to `str` for the closure below.
    browser = shutil.which("agent-browser") or pytest.skip(
        "agent-browser is not on PATH"
    )

    session = ["--session", f"weaver-tests-{os.getpid()}"]

    def run(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [browser, *args, *session],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        return completed.stdout

    try:
        yield run
    finally:
        # A session left open strands a browser daemon holding the viewport it
        # was last set to.
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [browser, "close", *session],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            timeout=TOOL_TIMEOUT_SECONDS,
        )


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    """Load the icon generator the way running the script by path would.

    It imports `weaver_icons_template` as a bare name, which works because a
    script run by path has its own directory on `sys.path`; the shared loader
    reproduces that.
    """
    return load("generate_weaver_icons")
