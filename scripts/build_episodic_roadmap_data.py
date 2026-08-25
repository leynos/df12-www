"""Generate the committed Episodic roadmap data template from its source.

The upstream Episodic ``docs/roadmap.md`` is authoritative for delivery state.
This script projects it into ``templates/episodic/data/roadmap.jinja`` so the
published subsite carries the same completion states without a source checkout
at site-build time. Run ``--check`` to fail when the committed projection has
drifted.
"""

from __future__ import annotations

import argparse
import dataclasses as dc
import json
import sys
from pathlib import Path

from episodic_roadmap_parser import Phase, load_roadmap

BANNER = (
    "{#\n"
    "  GENERATED FILE - do not edit by hand.\n"
    "\n"
    "  Projected from the upstream Episodic roadmap, which is authoritative\n"
    "  for delivery state. Regenerate with `make site-data` after the\n"
    "  upstream roadmap changes; `make check-site-data` fails when this file drifts.\n"
    "\n"
    "  Source: SOURCE\n"
    "#}\n"
)


def phase_payload(phase: Phase) -> dict[str, object]:
    """Return the serialisable template-facing projection of ``phase``."""
    return {
        "number": phase.number,
        "title": phase.title,
        "anchor": phase.anchor,
        "summary": phase.summary,
        "state": phase.state,
        "done_count": phase.done_count,
        "total_count": phase.total_count,
        "steps": [
            {
                "id": step.id,
                "title": step.title,
                "anchor": step.anchor,
                "summary": step.summary,
                "done_count": step.done_count,
                "total_count": len(step.tasks),
                "tasks": [
                    {key: value for key, value in dc.asdict(task).items() if value}
                    | {"done": task.done, "id": task.id, "title": task.title}
                    for task in step.tasks
                ],
            }
            for step in phase.steps
        ],
    }


def render(phases: list[Phase], source: str) -> str:
    """Render the complete Jinja data template for parsed ``phases``."""
    payload = [phase_payload(phase) for phase in phases]
    totals = {
        "done": sum(item["done_count"] for item in payload),  # type: ignore[misc]
        "total": sum(item["total_count"] for item in payload),  # type: ignore[misc]
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    summary = json.dumps(totals, indent=2, ensure_ascii=False)
    return (
        BANNER.replace("SOURCE", source)
        + f"{{% set roadmap_phases = {body} %}}\n"
        + f"{{% set roadmap_totals = {summary} %}}\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse source, output, and drift-check command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodic-root",
        type=Path,
        default=Path("../episodic"),
        help="Episodic checkout supplying the authoritative roadmap.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("templates/episodic/data/roadmap.jinja"),
        help="Generated Jinja data template.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed projection differs from the upstream roadmap.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate or verify the committed roadmap projection."""
    args = parse_args(argv)
    roadmap = args.episodic_root / "docs/roadmap.md"
    if not roadmap.is_file():
        print(f"Upstream roadmap not found at {roadmap}.", file=sys.stderr)
        return 1

    rendered = render(load_roadmap(roadmap), "leynos/episodic docs/roadmap.md")
    if args.check:
        current = (
            args.output.read_text(encoding="utf-8") if args.output.is_file() else ""
        )
        if current != rendered:
            print(
                f"{args.output} is stale. Run `make site-data` to regenerate it.",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output} matches the upstream roadmap.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
