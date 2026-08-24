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

from ruamel.yaml import YAML, YAMLError

# How a file's text becomes a document. Passing it in rather than branching on
# the file type keeps the read-and-report path in one place for both inputs.
type _Parser = cabc.Callable[[str], typ.Any]

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING = REPO_ROOT / "config" / "weaver-icons.yaml"
CARBON = REPO_ROOT / "node_modules" / "@iconify-json" / "carbon" / "icons.json"
OUTPUT = REPO_ROOT / "templates" / "weaver" / "_icons.jinja"

HEADER = """{#
  GENERATED FILE - do not edit.

  Written by scripts/generate_weaver_icons.py from config/weaver-icons.yaml
  and the @iconify-json/carbon package. Change the mapping, rerun the
  generator, and commit both; tests/test_weaver_build.py fails if this file
  and the mapping disagree.

  `icon(name)` takes a Font Awesome name without its `fa-` prefix, so a
  template that used to read

      <i class="fa-solid fa-terminal"></i>

  now reads

      {{ icon('terminal') }}

  The `extra_class` argument carries per-instance utilities, as the `<i>` did.
  The default size of 1em with a -0.125em baseline shift matches how a
  font-rendered glyph sat in its line, so the substitution does not move text
  around it.
#}
{%- macro icon(name, extra_class='') -%}
{%- set paths = {
"""

# The <svg> attributes, split so this file stays inside the line limit; the
# generated template joins them onto one line.
_SVG_CLASS = 'class="inline-block align-[-0.125em] w-[1em] h-[1em] {{ extra_class }}"'
_SVG_ATTRS = (
    'viewBox="0 0 32 32" fill="currentColor" aria-hidden="true" focusable="false"'
)

FOOTER = """} -%}
{%- set body = paths.get(name) -%}
{%- if body -%}
<svg __SVG__>{{ body | safe }}</svg>
{%- else -%}
{#- An unmapped name is a mistake in the caller, not something to hide. -#}
{{- ('UNKNOWN ICON: ' ~ name) -}}
{%- endif -%}
{%- endmacro -%}
"""


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
        If the name is neither an icon nor an alias.
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


def _entry(document: typ.Any, key: str, path: Path) -> dict[str, dict[str, str]]:  # noqa: ANN401 - the documents are untyped upstream data
    """Pull a required top-level mapping out of a parsed document, or exit.

    The value's shape is checked here rather than left to the first
    subscript in the renderer, where the failure surfaces as ``'int' object is
    not subscriptable`` and names neither the key nor the file.

    Parameters
    ----------
    document
        A parsed document, of whatever shape the file happened to hold.
    key
        The key the rest of this script needs.
    path
        The file the document came from, for the message.

    Returns
    -------
    dict
        The mapping at ``key``.

    Raises
    ------
    SystemExit
        If the document is not a mapping, has no such key, or holds something
        other than a mapping there.
    """
    entry = document.get(key) if isinstance(document, cabc.Mapping) else None
    if not isinstance(entry, cabc.Mapping):
        message = f"{path} has no top-level {key!r} mapping; its format has changed"
        raise SystemExit(message)
    return dict(entry)


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
        If either input file is absent, unreadable, malformed, or has lost the
        top-level key this script reads; or if the mapping names a Carbon icon
        the package does not define.
    """
    package = _read_document(CARBON, json.loads, "run 'bun install'")
    icons = _entry(package, "icons", CARBON)
    aliases = package.get("aliases", {})

    yaml = YAML(typ="safe")
    mapping = _entry(
        _read_document(MAPPING, yaml.load, "it is tracked, so restore it"),
        "icons",
        MAPPING,
    )

    try:
        return render_macro(icons, aliases, mapping)
    except KeyError as exc:
        message = f"{MAPPING} names a Carbon icon the package does not define: {exc}"
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
        here when reading or writing ``OUTPUT`` fails, for example because of
        permissions, a read-only tree, or a full disk. Every message names the
        file at fault.
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
    try:
        OUTPUT.write_text(macro, encoding="utf-8")
    except OSError as exc:
        message = f"{OUTPUT} could not be written ({exc})"
        raise SystemExit(message) from exc
    sys.stdout.write("_icons.jinja updated\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
