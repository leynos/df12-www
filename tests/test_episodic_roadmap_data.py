"""Regression tests for the owned Episodic roadmap projector."""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from scripts.build_episodic_roadmap_data import main
from scripts.episodic_roadmap_parser import Task, parse_roadmap

REPO_ROOT = Path(__file__).resolve().parent.parent


class RoadmapTaskRecord(typ.TypedDict):
    """JSON-compatible generated task data."""

    id: str
    title: str
    done: bool
    requires: typ.NotRequired[list[str]]
    notes: typ.NotRequired[list[str]]


class RoadmapStepRecord(typ.TypedDict):
    """JSON-compatible generated roadmap step data."""

    id: str
    title: str
    anchor: str
    summary: str
    done_count: int
    total_count: int
    tasks: list[RoadmapTaskRecord]


class RoadmapPhaseRecord(typ.TypedDict):
    """JSON-compatible generated roadmap phase data."""

    number: str
    title: str
    anchor: str
    summary: str
    state: str
    done_count: int
    total_count: int
    steps: list[RoadmapStepRecord]


def _task_from(markdown: str) -> Task:
    """Return the only task parsed from a minimal roadmap fixture."""
    phases = parse_roadmap(markdown)
    return phases[0].steps[0].tasks[0]


def test_title_dependency_sentence_expands_ranges_without_changing_the_title() -> None:
    """A title continuation moves its dependency range into ``requires``."""
    task = _task_from(
        "## 3. Phase\n\n"
        "### 3.3. Step\n\n"
        "- [ ] 3.3.6. Keep `inline code` in the title.\n"
        "  Requires 3.3.1-3.3.5.\n"
    )

    assert task.title == "Keep `inline code` in the title.", (
        "title dependency extraction must preserve unrelated inline-code content"
    )
    assert task.requires == ["3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5"], (
        "title dependency ranges must expand into every required task identifier"
    )
    assert task.notes == [], "title dependency extraction must not create notes"


def test_first_note_dependency_sentence_preserves_the_remaining_note() -> None:
    """A leading dependency note moves into ``requires`` without losing prose."""
    task = _task_from(
        "## 4. Phase\n\n"
        "### 4.3. Step\n\n"
        "- [ ] 4.3.1. Keep this title.\n"
        "  - Requires 1.3.4, 1.4.3, and 4.1.1. Preserve this note.\n"
        "  - Keep this unrelated note.\n"
    )

    assert task.title == "Keep this title.", (
        "first-note dependency extraction must not change the task title"
    )
    assert task.requires == ["1.3.4", "1.4.3", "4.1.1"], (
        "first-note dependencies must populate the dedicated requires field"
    )
    assert task.notes == ["Preserve this note.", "Keep this unrelated note."], (
        "first-note dependency extraction must retain remaining and later notes"
    )


def test_generated_dependency_fields_drive_the_roadmap_task_macro() -> None:
    """The four normalized tasks render dependency lines from ``task.requires``."""
    environment = Environment(
        autoescape=True,
        loader=FileSystemLoader(REPO_ROOT / "templates/episodic"),
    )
    roadmap_phases = typ.cast(
        "list[RoadmapPhaseRecord]",
        json.loads(
            environment.from_string(
                '{% from "data/roadmap.jinja" import roadmap_phases %}'
                "{{ roadmap_phases | tojson }}"
            ).render()
        ),
    )
    tasks: dict[str, RoadmapTaskRecord] = {
        task["id"]: task
        for phase in roadmap_phases
        for step in phase["steps"]
        for task in step["tasks"]
    }
    expected = {
        "3.3.6": ["3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5"],
        "3.6.1": ["3.1.1", "3.1.4", "3.3.1", "3.3.3", "3.3.4"],
        "4.3.1": ["1.3.4", "1.4.3", "4.1.1"],
        "4.3.2": ["2.1.1", "2.4.2", "4.3.1"],
    }

    assert {task_id: tasks[task_id]["requires"] for task_id in expected} == expected, (
        "the generated four-task fixture must use the expected requires arrays"
    )
    assert all(
        "Requires " not in tasks[task_id]["title"]
        and not tasks[task_id].get("notes", [""])[0].startswith("Requires ")
        for task_id in expected
    ), "generated dependency sentences must be removed from titles and first notes"

    rendered = environment.from_string(
        '{% import "records.jinja" as rec %}'
        "{% for task in tasks %}{{ rec.roadmap_task(task) }}{% endfor %}"
    ).render(tasks=[tasks[task_id] for task_id in expected])
    rendered_dependencies = [
        dependency.get_text(" ", strip=True)
        for dependency in BeautifulSoup(rendered, "html.parser").select(
            ".task__requires"
        )
    ]
    assert rendered_dependencies == [
        f"Requires {', '.join(requirements)}" for requirements in expected.values()
    ], "records.roadmap_task must render each generated requires array"


def test_projector_generates_and_checks_a_temporary_roadmap(tmp_path: Path) -> None:
    """The command projects source data, accepts matching output, and detects drift."""
    source = tmp_path / "episodic source"
    roadmap = source / "docs" / "roadmap.md"
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(
        "## 1. Phase\n\n"
        "### 1.1. Step\n\n"
        "- [x] 1.1.1. Complete the first task.\n"
        "- [ ] 1.1.2. Complete the second task. Requires 1.1.1.\n",
        encoding="utf-8",
    )
    output = tmp_path / "generated" / "roadmap.jinja"
    arguments = ["--episodic-root", str(source), "--output", str(output)]

    assert main(arguments) == 0, "projector must generate a missing output file"
    rendered = output.read_text(encoding="utf-8")
    assert '"requires": [\n              "1.1.1"\n            ]' in rendered, (
        "projector output must contain normalized dependency data"
    )
    assert main([*arguments, "--check"]) == 0, (
        "projector check must accept a matching generated file"
    )

    output.write_text("stale\n", encoding="utf-8")
    assert main([*arguments, "--check"]) == 1, (
        "projector check must reject output that drifts from its source roadmap"
    )
