"""The literal text `_icons.jinja` is built from.

Kept apart from the generator because it is data rather than logic: a Jinja
template written as Python strings, which reads badly interleaved with the
code that fills it in and changes for entirely different reasons.
"""

from __future__ import annotations

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
{#- The dictionary is built once, at template scope, rather than inside the
    macro. Inside it, Jinja rebuilt all fifty-three entries on every `icon()`
    call, and a page renders dozens. -#}
{%- set paths = {
"""

# The <svg> attributes, split so this file stays inside the line limit; the
# generated template joins them onto one line.
_SVG_CLASS = 'class="inline-block align-[-0.125em] w-[1em] h-[1em] {{ extra_class }}"'

_SVG_ATTRS = (
    'viewBox="0 0 32 32" fill="currentColor" aria-hidden="true" focusable="false"'
)

FOOTER = """} -%}
{%- macro icon(name, extra_class='') -%}
{%- set body = paths.get(name) -%}
{%- if body -%}
<svg __SVG__>{{ body | safe }}</svg>
{%- else -%}
{#- An unmapped name is a mistake in the caller, not something to hide. -#}
{{- ('UNKNOWN ICON: ' ~ name) -}}
{%- endif -%}
{%- endmacro -%}
"""
