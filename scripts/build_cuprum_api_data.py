"""Generate the Cuprum sub-site's API reference data from Cuprum's source.

The API pages under ``/cuprum/docs/api/`` render every name Cuprum exports.
This script reads them from a Cuprum checkout at the documented release with
:mod:`cuprum_api_parser`, sorts them into the site's reference pages, and
writes ``templates/cuprum/data/api.jinja`` so the site builds without a Cuprum
checkout. Run it after the pinned release moves; ``--check`` fails when the
committed data no longer matches the source.

Every exported name, and each public submodule in :data:`EXTRA_MODULES`, must
belong to exactly one page in :data:`GROUPS`, so a name Cuprum adds cannot slip
out of the reference unnoticed.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tomllib
import typing as typ
from pathlib import Path

if __package__:
    from .atomic_write import atomic_write
    from .cuprum_api_parser import SECTION_NAMES, ApiEntry, Docstring, Member, load_api
else:
    from atomic_write import atomic_write
    from cuprum_api_parser import SECTION_NAMES, ApiEntry, Docstring, Member, load_api

#: The reference pages, in reading order: slug, title, lede, and the exported
#: names each documents, in the order they appear on the page.
GROUPS: tuple[dict[str, typ.Any], ...] = (
    {
        "slug": "commands",
        "title": "Commands and results",
        "lede": (
            "Building a typed command from a catalogued program, running it, "
            "and reading what it returns."
        ),
        "names": (
            "sh",
            "SafeCmd",
            "SafeCmdBuilder",
            "CommandResult",
            "ExecutionContext",
            "RunOutputOptions",
            "IOOptions",
            "StdinInput",
            "LineStream",
            "LineEvent",
            "LineHook",
            "LineStreamName",
            "builders",
        ),
    },
    {
        "slug": "catalogues",
        "title": "Programs and catalogues",
        "lede": (
            "The programs Cuprum may build commands for, the projects that "
            "group them, and the defaults it ships."
        ),
        "names": (
            "Program",
            "ProgramCatalogue",
            "ProgramEntry",
            "ProjectSettings",
            "DEFAULT_CATALOGUE",
            "DEFAULT_PROJECTS",
            "CORE_OPS_PROJECT",
            "DOCUMENTATION_PROJECT",
            "ECHO",
            "GIT",
            "LS",
            "RSYNC",
            "TAR",
            "DOC_TOOL",
            "PACKAGE_NAME",
            "cuprum.catalogue",
        ),
    },
    {
        "slug": "pipelines",
        "title": "Pipelines and concurrency",
        "lede": (
            "Joining commands stage to stage, and running independent commands "
            "side by side."
        ),
        "names": (
            "Pipeline",
            "PipelineResult",
            "run_concurrent",
            "run_concurrent_sync",
            "ConcurrentConfig",
            "ConcurrentResult",
        ),
    },
    {
        "slug": "policy",
        "title": "Scopes, policy, and hooks",
        "lede": (
            "Narrowing what a block of code may run, overlaying its "
            "environment, and running code around each command."
        ),
        "names": (
            "scoped",
            "ScopeConfig",
            "CuprumContext",
            "current_context",
            "get_context",
            "allow",
            "AllowRegistration",
            "env",
            "EnvRegistration",
            "merge_env_overlays",
            "resolve_env",
            "before",
            "after",
            "BeforeHook",
            "AfterHook",
            "HookRegistration",
        ),
    },
    {
        "slug": "observation",
        "title": "Events and observation",
        "lede": "The structured events a run emits, and the hooks that receive them.",
        "names": (
            "observe",
            "ExecEvent",
            "ExecHook",
            "logging_hook",
            "LoggingHookRegistration",
            "observe_line_stream",
            "LineStreamEvent",
            "LineStreamHook",
            "LineStreamHookRegistration",
            "LineStreamPhase",
            "LineStreamSink",
            "observe_echo",
            "EchoEvent",
            "EchoHook",
            "EchoHookRegistration",
            "EchoStream",
            "EchoErrorCategory",
            "RelayFallback",
            "cuprum.stream_observation",
        ),
    },
    {
        "slug": "rust",
        "title": "Rust pump and backends",
        "lede": (
            "Whether the optional native pump is present, and what it reports "
            "when a pipeline hop uses it or falls back."
        ),
        "names": (
            "is_rust_available",
            "observe_pump",
            "PumpEvent",
            "PumpHook",
            "PumpHookRegistration",
            "RustPumpDeclineReason",
            "RustPumpHandoffOutcome",
            "observe_pump_span",
            "PumpHopSpanRegistration",
            "PumpHopOutcome",
        ),
    },
    {
        "slug": "adapters",
        "title": "Adapters and sinks",
        "lede": (
            "Ready-made observe hooks for logging, metrics, and tracing; metrics "
            "for stream operations, line events, echo, and the Rust pump; and the "
            "output sink that frames a run for GitHub Actions."
        ),
        "names": (
            "cuprum.adapters.logging_adapter",
            "cuprum.adapters.metrics_adapter",
            "cuprum.adapters.tracing_adapter",
            "cuprum.adapters.stream_metrics",
            "cuprum.adapters.line_stream_metrics",
            "cuprum.adapters.echo_metrics",
            "cuprum.adapters.pump_metrics",
            "cuprum.sinks",
        ),
    },
    {
        "slug": "errors",
        "title": "Errors",
        "lede": (
            "The exceptions Cuprum raises when a program is unknown, forbidden, "
            "or too slow."
        ),
        "names": ("UnknownProgramError", "ForbiddenProgramError", "TimeoutExpired"),
    },
)

#: Public submodules the package does not re-export, documented as module
#: entries alongside ``__all__``: the guide's recipes import from them.
EXTRA_MODULES = (
    "cuprum.catalogue",
    "cuprum.stream_observation",
    "cuprum.sinks",
    "cuprum.adapters.logging_adapter",
    "cuprum.adapters.metrics_adapter",
    "cuprum.adapters.tracing_adapter",
    "cuprum.adapters.stream_metrics",
    "cuprum.adapters.line_stream_metrics",
    "cuprum.adapters.echo_metrics",
    "cuprum.adapters.pump_metrics",
)

BANNER = """{#
  GENERATED FILE - do not edit by hand.

  The Cuprum API reference, read from Cuprum's source by
  scripts/build_cuprum_api_data.py. Regenerate with `make cuprum-api-data`
  after the documented release moves; `make check-cuprum-api-data` fails when
  this file no longer matches the source.

  Source: SOURCE
#}
"""

_LITERAL = re.compile(r"``(.+?)``")
_ROLE = re.compile(r":(?:class|func|meth|attr|data|exc|mod|obj):`~?([^`]+)`")
_BACKTICK = re.compile(r"(?<![`\w])`([^`]+)`(?![`\w])")


#: Signatures longer than this are set one parameter to a line.
WRAP_WIDTH = 72


def _split_top_level(params: str) -> list[str]:
    """Split a parameter list at commas that are not nested in brackets."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in params:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return parts


def display_line(kind: str, name: str, signature: str) -> str:
    """Return the declaration line a reference entry shows for ``name``.

    Parameters
    ----------
    kind : str
        The entry's kind: ``class``, ``exception``, ``function``, ``method``,
        ``classmethod``, ``staticmethod``, ``property``, ``field``,
        ``member``, ``constant``, ``alias``, ``type alias``, ``new type``, or
        ``module``.
    name : str
        The name being declared. A module is shown as the import that reaches
        it, since its declaration would say nothing.
    signature : str
        The parameters and return annotation, or the ``= value`` or
        ``: annotation`` suffix, as the parser rendered it.

    Returns
    -------
    str
        A Python-like declaration. Parameter lists longer than
        :data:`WRAP_WIDTH` are set one parameter to a line.

    Examples
    --------
    >>> display_line("function", "make", "(program: Program) -> SafeCmdBuilder")
    'def make(program: Program) -> SafeCmdBuilder'
    """
    if kind == "module":
        parent, _, leaf = name.rpartition(".")
        return f"from {parent or 'cuprum'} import {leaf}"
    if not signature.startswith(("(", "async (")):
        return f"{name}{signature}"
    is_async = signature.startswith("async ")
    signature = signature.removeprefix("async ")
    keyword = {"class": "class ", "exception": "class "}.get(kind, "def ")
    if kind == "property":
        keyword = ""
    close = _matching_paren(signature)
    parts = [_spaced_default(part) for part in _split_top_level(signature[1:close])]
    tail = signature[close + 1 :]
    prefix = f"{'async ' if is_async else ''}{keyword}{name}"
    flat = f"{prefix}({', '.join(parts)}){tail}"
    if len(flat) <= WRAP_WIDTH or not parts:
        return flat
    lines = "".join(f"    {part},\n" for part in parts)
    return f"{prefix}(\n{lines}){tail}"


def _spaced_default(param: str) -> str:
    """Space an annotated parameter's default as PEP 8 sets it: ``a: T = d``."""
    depth = 0
    for index, char in enumerate(param):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "=" and depth == 0:
            head, default = param[:index].rstrip(), param[index + 1 :].lstrip()
            return f"{head} = {default}" if ":" in head else f"{head}={default}"
    return param


def _matching_paren(text: str) -> int:
    """Return the index of the parenthesis closing the one at index 0."""
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return len(text) - 1


class GroupingError(Exception):
    """Raised when the exported names and :data:`GROUPS` disagree."""


def inline_html(text: str, known: frozenset[str]) -> str:
    """Render reStructuredText inline markup in ``text`` as escaped HTML.

    Parameters
    ----------
    text : str
        Docstring prose, with ````literal````, ```reference```, and
        ``:role:`target``` markup.
    known : frozenset[str]
        Exported names; a role naming one becomes a link to its entry.

    Returns
    -------
    str
        HTML-escaped text in which literals and references are ``<code>``
        elements, and references to exported names link to their anchors.

    Examples
    --------
    >>> known = frozenset({"SafeCmd"})
    >>> inline_html("Returns ``int`` from :class:`SafeCmd`.", known)
    'Returns <code>int</code> from <a href="#SafeCmd"><code>SafeCmd</code></a>.'
    """
    parts: list[str] = []
    for index, piece in enumerate(_LITERAL.split(text)):
        if index % 2:
            parts.append(f"<code>{html.escape(piece)}</code>")
            continue
        escaped = html.escape(piece, quote=False)
        escaped = _ROLE.sub(lambda m: _reference(m[1], known), escaped)
        escaped = _BACKTICK.sub(lambda m: _reference(m[1], known), escaped)
        parts.append(escaped)
    return "".join(parts)


def _reference(target: str, known: frozenset[str]) -> str:
    """Render a cross-reference, linking it when it names an exported entry."""
    label = target.rsplit(".", 1)[-1] if target.startswith(("cuprum.", "~")) else target
    code = f"<code>{label}</code>"
    head = label.split(".", 1)[0].removesuffix("()")
    return f'<a href="#{head}">{code}</a>' if head in known else code


def _doc_payload(doc: Docstring, known: frozenset[str]) -> dict[str, typ.Any]:
    """Project a parsed docstring into template-ready HTML fragments."""
    payload: dict[str, typ.Any] = {"summary": inline_html(doc.summary, known)}
    if doc.body:
        payload["body"] = [inline_html(p, known) for p in doc.body]
    sections = []
    for name in SECTION_NAMES:
        section: dict[str, typ.Any] = {"title": name}
        if doc.fields.get(name):
            section["fields"] = [
                {
                    "name": field.name,
                    "type": html.escape(field.type),
                    "description": inline_html(field.description, known),
                }
                for field in doc.fields[name]
            ]
        if doc.texts.get(name):
            section["paragraphs"] = [inline_html(p, known) for p in doc.texts[name]]
        if len(section) > 1:
            sections.append(section)
    if sections:
        payload["sections"] = sections
    if doc.examples:
        payload["examples"] = doc.examples
    return payload


def _member_payload(member: Member, known: frozenset[str]) -> dict[str, typ.Any]:
    """Project a class or module member for the templates."""
    return {
        "name": member.name,
        "kind": member.kind,
        "display": display_line(member.kind, member.name, member.signature),
        "doc": _doc_payload(member.doc, known),
    }


def _entry_payload(entry: ApiEntry, known: frozenset[str]) -> dict[str, typ.Any]:
    """Project one exported name for the templates."""
    payload: dict[str, typ.Any] = {
        "name": entry.name,
        "kind": entry.kind,
        "module": entry.module,
        "path": entry.path,
        "line": entry.line,
        "display": display_line(entry.kind, entry.name, entry.signature),
        "doc": _doc_payload(entry.doc, known),
    }
    if entry.bases:
        payload["bases"] = list(entry.bases)
    if entry.members:
        payload["members"] = [_member_payload(m, known) for m in entry.members]
    return payload


def group_entries(entries: list[ApiEntry]) -> list[dict[str, typ.Any]]:
    """Sort exported entries into the reference pages of :data:`GROUPS`.

    Parameters
    ----------
    entries : list[cuprum_api_parser.ApiEntry]
        Every exported name, as :func:`cuprum_api_parser.load_api` returns it.

    Returns
    -------
    list[dict[str, typing.Any]]
        One mapping per page, with its slug, title, lede, and entries.

    Raises
    ------
    GroupingError
        If a name is exported but on no page, on two pages, or on a page but
        no longer exported.
    """
    by_name = {entry.name: entry for entry in entries}
    known = frozenset(by_name)
    placed = [name for group in GROUPS for name in group["names"]]
    duplicates = sorted({name for name in placed if placed.count(name) > 1})
    missing = sorted(known - set(placed))
    stale = sorted(set(placed) - known)
    if duplicates or missing or stale:
        msg = (
            f"API grouping is out of date: unplaced {missing}, "
            f"placed twice {duplicates}, no longer exported {stale}"
        )
        raise GroupingError(msg)
    return [
        {
            "slug": group["slug"],
            "title": group["title"],
            "lede": group["lede"],
            "entries": [
                _entry_payload(by_name[name], known) for name in group["names"]
            ],
        }
        for group in GROUPS
    ]


def source_identity(root: Path) -> dict[str, str]:
    """Return the checkout's package version and commit.

    Parameters
    ----------
    root : Path
        The Cuprum checkout.

    Returns
    -------
    dict[str, str]
        ``version`` from ``pyproject.toml`` and the full ``commit`` SHA.
    """
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    commit = subprocess.run(  # noqa: S603 - fixed argv; the path is the checkout root
        ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607 - git is resolved on PATH
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {"version": str(project["project"]["version"]), "commit": commit}


def render(groups: list[dict[str, typ.Any]], identity: dict[str, str]) -> str:
    """Render the complete Jinja data template.

    Parameters
    ----------
    groups : list[dict[str, typing.Any]]
        The grouped reference pages from :func:`group_entries`.
    identity : dict[str, str]
        The source's ``version`` and ``commit``.

    Returns
    -------
    str
        The banner and the ``api_groups`` and ``api_source`` declarations.
    """
    source = f"leynos/cuprum {identity['version']} at {identity['commit']}"
    body = json.dumps(groups, indent=2, ensure_ascii=False)
    meta = json.dumps(identity, indent=2, ensure_ascii=False)
    return (
        BANNER.replace("SOURCE", source)
        + f"{{% set api_groups = {body} %}}\n"
        + f"{{% set api_source = {meta} %}}\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the source, output, and drift-check arguments.

    Parameters
    ----------
    argv : list[str] | None
        Argument vector, or ``None`` to read the process arguments.

    Returns
    -------
    argparse.Namespace
        The Cuprum checkout, the output path, and the check-mode flag.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cuprum-root",
        type=Path,
        default=Path("../cuprum"),
        help="Cuprum checkout at the documented release.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("templates/cuprum/data/api.jinja"),
        help="Generated Jinja data template.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed data differs from the source.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate or check the API reference data.

    Parameters
    ----------
    argv : list[str] | None
        Argument vector, or ``None`` to read the process arguments.

    Returns
    -------
    int
        ``0`` on success; ``1`` when ``--check`` finds drift.
    """
    args = parse_args(argv)
    groups = group_entries(load_api(args.cuprum_root, "cuprum", EXTRA_MODULES))
    rendered = render(groups, source_identity(args.cuprum_root))
    if args.check:
        current = (
            args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        )
        if current != rendered:
            print(
                f"{args.output} is out of date; run `make cuprum-api-data`.",
                file=sys.stderr,
            )
            return 1
        return 0
    atomic_write(args.output, rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
