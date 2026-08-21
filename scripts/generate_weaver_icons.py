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

import json
import sys
from pathlib import Path

from ruamel.yaml import YAML

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


def build_macro() -> str:
    """Render the icon macro from the mapping and the Carbon package.

    Returns
    -------
    str
        The complete contents of ``templates/weaver/_icons.jinja``.

    Raises
    ------
    SystemExit
        If the Carbon package is absent, with the command that installs it.
    """
    if not CARBON.is_file():
        message = f"{CARBON} is missing; run 'bun install'"
        raise SystemExit(message)

    package = json.loads(CARBON.read_text(encoding="utf-8"))
    icons = package["icons"]
    aliases = package.get("aliases", {})

    yaml = YAML(typ="safe")
    mapping = yaml.load(MAPPING.read_text(encoding="utf-8"))["icons"]

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


def main() -> int:
    """Rewrite the generated macro if it differs from the current file."""
    macro = build_macro()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if macro != current:
        OUTPUT.write_text(macro, encoding="utf-8")
        sys.stdout.write("_icons.jinja updated\n")
    else:
        sys.stdout.write("_icons.jinja unchanged\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
