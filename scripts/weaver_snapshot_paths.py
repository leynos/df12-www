"""Where the snapshot harness reads from and writes to.

The published tree it captures, the page list it derives from that tree, and
the filename each page's snapshot takes. Kept apart from the rest because
nothing here starts a process or opens a socket: it is the part that can be
reasoned about by reading it.

The harness was written for Weaver and its modules still carry that name; the
sub-site is a parameter now, so the same tooling drives the Netsuke migration.
``DEFAULT_SITE`` keeps every existing call and command meaning what it did.
"""

from __future__ import annotations

import os
import re
import typing as typ
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC = REPO_ROOT / "public"
HTTP_SERVER = REPO_ROOT / "node_modules" / ".bin" / "http-server"

# The sub-site every command and helper serves when none is named.
DEFAULT_SITE = "weaver"

# What a sub-site name may look like: the `sites:` keys in config/pages.yaml
# are lower-case slugs, and the name is spliced into a filesystem path and a
# URL, so anything else is refused rather than resolved.
SITE_NAME = re.compile(r"[a-z][a-z0-9-]*")


def _public_root(site: str = DEFAULT_SITE) -> Path:
    """Locate one sub-site's published tree.

    Parameters
    ----------
    site
        The sub-site's name as it appears under ``sites:`` in
        ``config/pages.yaml`` and as the first segment of its URLs.

    Returns
    -------
    Path
        ``public/<site>``.

    Raises
    ------
    SystemExit
        If the name is not a plain lower-case slug. The name becomes a path
        segment and a URL segment, so ``../`` or a space would not point at a
        sub-site at all.
    """
    if not SITE_NAME.fullmatch(site):
        message = f"{site!r} is not a sub-site name; expected a slug such as 'weaver'"
        raise SystemExit(message)
    return PUBLIC / site


PUBLIC_WEAVER = _public_root(DEFAULT_SITE)


def _page_paths(root: Path = PUBLIC_WEAVER) -> list[str]:
    """List one sub-site's published pages as base-relative URL paths.

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
        Paths relative to the sub-site's base path, such as ``""`` for the
        home page and ``"commands/act/"`` for a nested one, in sorted order.

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
        A path relative to the sub-site's base path, such as
        ``"commands/act/"``.

    Returns
    -------
    str
        A flat, filesystem-safe stem: ``"__home"`` for the home page and
        ``"commands__act"`` for the example above.
    """
    return page.strip("/").replace("_", "_u").replace("/", "__") or "__home"


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
