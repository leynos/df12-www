"""Guard the committed site configuration against retired project pages."""

from pathlib import Path

import pytest

from df12_pages.config import load_site_config

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("retired_key", ["pylint-pypy-shim"])
def test_committed_config_publishes_no_retired_project_page(
    retired_key: str,
) -> None:
    """A retired project must not be built into the docs hub or its index.

    The shim repository is archived because plain Pylint runs on PyPy 3.12; the
    hub iterates `pages`, so a lingering entry would publish a page for it.
    """
    site_config = load_site_config(REPO_ROOT / "config" / "pages.yaml")

    assert retired_key not in site_config.pages, (
        f"{retired_key} is retired and must not be a configured docs page"
    )
    assert site_config.pages, "the committed configuration must still list pages"
