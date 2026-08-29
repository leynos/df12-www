"""Regenerate the Weaver sub-site's inline icon macro.

Reads the Font Awesome to Carbon mapping in ``config/weaver-icons.yaml``,
pulls each icon's path data out of the ``@iconify-json/carbon`` package, and
writes ``templates/weaver/_icons.jinja``: a Jinja macro that inlines the SVG
directly into the page.

    uv run python scripts/generate_weaver_icons.py

This mirrors ``generate_himotoshi_pygments_css.py`` and
``generate_stilyagi_pygments_css.py``, which do the same for the syntax
stylesheets: the output is committed, never hand-edited, and a test fails if
the committed file drifts from what this script produces.

Inlining rather than linking a sprite or a runtime icon script is the point.
The sub-site used to fetch Font Awesome from a CDN twice per page — once as a
stylesheet, once as the SVG-replacement script — and the published pages now
carry the artwork themselves and fetch nothing.
"""

from __future__ import annotations

import collections.abc as cabc
import json
import sys
import typing as typ
from pathlib import Path

from atomic_write import atomic_write
from ruamel.yaml import YAML, YAMLError
from weaver_icons_template import _SVG_ATTRS, _SVG_CLASS, FOOTER, HEADER

# How a file's text becomes a document. Passing it in rather than branching on
# the file type keeps the read-and-report path in one place for both inputs.
type _Parser = cabc.Callable[[str], typ.Any]

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING = REPO_ROOT / "config" / "weaver-icons.yaml"
CARBON = REPO_ROOT / "node_modules" / "@iconify-json" / "carbon" / "icons.json"
OUTPUT = REPO_ROOT / "templates" / "weaver" / "_icons.jinja"


def _resolve(
    icons: dict[str, dict[str, str]], aliases: dict[str, dict[str, str]], name: str
) -> str:
    """Return the SVG body for one Carbon icon, following any alias.

    Parameters
    ----------
    icons
        The package's ``icons`` mapping, keyed by icon name.
    aliases
        The package's ``aliases`` mapping, each entry naming a ``parent``.
    name
        A Carbon icon name, without the ``carbon:`` prefix.

    Returns
    -------
    str
        The icon's SVG body markup.

    Raises
    ------
    KeyError
        If the name is neither an icon nor an alias, or an alias chain loops.
        The records themselves are checked by :func:`_records` before this
        runs, so a missing ``parent`` or ``body`` cannot arise here.
    """
    seen: set[str] = set()
    while name in aliases and name not in icons:
        if name in seen:
            message = f"alias loop resolving carbon:{name}"
            raise KeyError(message)
        seen.add(name)
        name = aliases[name]["parent"]
    return icons[name]["body"]


def _read_document(path: Path, parse: _Parser, absent: str) -> typ.Any:  # noqa: ANN401 - the parsers return whatever their document holds
    """Read and parse one input file, or exit naming it.

    The three ways an input file can fail — absent, unreadable, unparseable —
    are indistinguishable to the caller once they surface as a bare
    ``FileNotFoundError`` or ``JSONDecodeError`` several frames up, and none
    of them names the file. Converting them here means every failure of this
    script says which file was at fault and, where the fix is known, what to
    run.

    Parameters
    ----------
    path
        The file to read, as UTF-8 text.
    parse
        Turns that text into a document. Raises for malformed input.
    absent
        What to tell the operator when the file is not there, beyond its path.

    Returns
    -------
    typing.Any
        Whatever ``parse`` returned.

    Raises
    ------
    SystemExit
        If the file is absent, unreadable, or malformed.
    """
    if not path.is_file():
        message = f"{path} is missing; {absent}"
        raise SystemExit(message)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"{path} could not be read ({exc})"
        raise SystemExit(message) from exc
    try:
        return parse(text)
    except (json.JSONDecodeError, YAMLError) as exc:
        message = f"{path} is malformed ({exc})"
        raise SystemExit(message) from exc


def _records(
    document: typ.Any,  # noqa: ANN401 - the documents are untyped upstream data
    key: str,
    field: str,
    path: Path,
    *,
    required: bool = True,
) -> dict[str, dict[str, str]]:
    """Pull a mapping of records out of a parsed document, checking each one.

    Both inputs are mappings of mappings, and every level of that is somebody
    else's format: the Carbon package's shape is upstream's to change, and the
    icon mapping is hand-edited. Checking only the outer level leaves the inner
    one to the first subscript in the renderer, where a scalar where a record
    was expected surfaces as ``'int' object is not subscriptable`` — a
    ``TypeError``, which the caller's ``except KeyError`` does not catch — and
    names neither the entry, nor the field, nor the file.

    So each record is checked here for being a mapping that carries ``field``
    as a string, which is the only thing the renderer asks of it.

    Parameters
    ----------
    document
        A parsed document, of whatever shape the file happened to hold.
    key
        The top-level key holding the records.
    field
        The field every record must carry, as a string.
    path
        The file the document came from, for the message.
    required
        Whether the key must be present. The Carbon package's ``aliases`` is
        optional; an icon set with no aliases is not malformed.

    Returns
    -------
    dict
        The records at ``key``, each one checked.

    Raises
    ------
    SystemExit
        If the document is not a mapping, if a required key is absent or holds
        something other than a mapping, or if any record is not a mapping
        carrying ``field`` as a string.
    """
    entries = document.get(key) if isinstance(document, cabc.Mapping) else None
    if entries is None and not required:
        return {}
    if not isinstance(entries, cabc.Mapping):
        message = f"{path} has no top-level {key!r} mapping; its format has changed"
        raise SystemExit(message)

    broken = sorted(
        str(name)
        for name, record in entries.items()
        if not isinstance(record, cabc.Mapping)
        or not isinstance(record.get(field), str)
    )
    if broken:
        message = (
            f"{path}: {len(broken)} of the {len(entries)} entries under {key!r} "
            f"do not carry a string {field!r}, starting with {broken[:5]}; "
            f"its format has changed"
        )
        raise SystemExit(message)
    return {str(name): dict(record) for name, record in entries.items()}


def render_macro(
    icons: dict[str, dict[str, str]],
    aliases: dict[str, dict[str, str]],
    mapping: dict[str, dict[str, str]],
) -> str:
    """Render the icon macro from data already read and parsed.

    Kept free of I/O so the rendering can be exercised on a handful of
    literal icons, without a ``node_modules`` tree or a mapping file.

    Parameters
    ----------
    icons
        The Carbon package's ``icons`` mapping, keyed by icon name.
    aliases
        The Carbon package's ``aliases`` mapping, each entry naming a
        ``parent``.
    mapping
        The Font Awesome to Carbon mapping, keyed by Font Awesome name, each
        entry carrying a ``carbon`` name.

    Returns
    -------
    str
        The complete contents of ``templates/weaver/_icons.jinja``.

    Raises
    ------
    KeyError
        If a mapped Carbon name is neither an icon nor an alias, or an alias
        chain loops. :func:`build_macro` converts this into a ``SystemExit``
        naming the mapping file.
    """
    entries = []
    for fa_name in sorted(mapping):
        carbon = mapping[fa_name]["carbon"].removeprefix("carbon:")
        body = _resolve(icons, aliases, carbon)
        # The bodies are single-quote-free path data, but quote defensively
        # rather than trusting an upstream package's punctuation.
        escaped = body.replace("\\", "\\\\").replace("'", "\\'")
        entries.append(f"  '{fa_name.removeprefix('fa-')}': '{escaped}',")

    footer = FOOTER.replace("__SVG__", f"{_SVG_CLASS} {_SVG_ATTRS}")
    return HEADER + "\n".join(entries) + "\n" + footer


def build_macro() -> str:
    """Read the mapping and the Carbon package, and render the icon macro.

    This is the I/O boundary: everything that can fail because of the
    filesystem or a malformed input fails here, as a ``SystemExit`` naming the
    file. :func:`render_macro` does the rendering and touches nothing.

    Returns
    -------
    str
        The complete contents of ``templates/weaver/_icons.jinja``.

    Raises
    ------
    SystemExit
        If either input file is absent, unreadable, malformed, has lost the
        top-level key this script reads, or holds a record that is not a
        mapping carrying the field the renderer needs; or if the mapping names
        a Carbon icon the package does not define.
    """
    package = _read_document(CARBON, json.loads, "run 'bun install'")
    icons = _records(package, "icons", "body", CARBON)
    aliases = _records(package, "aliases", "parent", CARBON, required=False)

    yaml = YAML(typ="safe")
    mapping = _records(
        _read_document(MAPPING, yaml.load, "it is tracked, so restore it"),
        "icons",
        "carbon",
        MAPPING,
    )

    try:
        return render_macro(icons, aliases, mapping)
    except KeyError as exc:
        message = f"{MAPPING} names a Carbon icon the package does not define: {exc}"
        raise SystemExit(message) from exc


def _publish_macro(macro: str, output: Path) -> None:
    """Replace ``output`` with ``macro``, or leave it exactly as it was.

    Writing straight into the committed file is not failure-atomic: a write
    that stops partway — a full disk, a signal — leaves a half-written macro
    where a valid one was, and the next build renders a template Jinja cannot
    parse. The file is generated, so it can always be regenerated; but only if
    the failure is visible, and a truncated file that still parses is not.

    So the macro goes through :func:`atomic_write` — a unique temporary file
    beside the target, moved into place with a rename. Until that rename the
    old contents are untouched, and after it they are wholly replaced.

    Parameters
    ----------
    macro
        The complete contents to publish.
    output
        The file to replace.

    Raises
    ------
    SystemExit
        If the temporary file cannot be created, written, closed, or moved
        into place, with a message naming ``output``.
    """
    try:
        atomic_write(output, macro)
    except OSError as exc:
        message = f"{output} could not be written ({exc}); it is unchanged"
        raise SystemExit(message) from exc


def main() -> int:
    """Regenerate the Weaver icon macro and report whether it changed.

    Builds the macro from the mapping and the Carbon package, then compares
    it against the existing ``templates/weaver/_icons.jinja``. When the two
    differ, ``OUTPUT`` (``templates/weaver/_icons.jinja``) is overwritten
    with the freshly built macro; when they match, the file is left alone.
    Either way, a one-line status is written to stdout.

    Returns
    -------
    int
        Always ``0``, on both the updated and unchanged paths. Failure is
        signalled through an exception rather than the return value, so a
        non-zero result never arises here.

    Raises
    ------
    SystemExit
        Propagated from ``build_macro`` when an input file is absent,
        unreadable, malformed, or names an icon the package lacks; and raised
        here when reading ``OUTPUT`` fails, or when publishing the new macro
        does — for example because of permissions, a read-only tree, or a full
        disk. Every message names the file at fault, and a failed publication
        leaves the previous macro in place.
    """
    macro = build_macro()
    try:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    except OSError as exc:
        message = f"{OUTPUT} could not be read ({exc})"
        raise SystemExit(message) from exc
    if macro == current:
        sys.stdout.write("_icons.jinja unchanged\n")
        return 0
    _publish_macro(macro, OUTPUT)
    sys.stdout.write("_icons.jinja updated\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
