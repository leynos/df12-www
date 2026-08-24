"""Fixtures shared between the Weaver suites.

``built_site`` lives here rather than in one test module because two suites
need it — ``test_weaver_build.py`` reads the published markup, and
``test_weaver_browser.py`` serves it to a real browser — and a full
``bun run build`` costs too much to run once per module.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

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
