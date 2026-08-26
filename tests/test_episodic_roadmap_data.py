"""Regression tests for the owned Episodic roadmap projector."""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

import scripts.build_episodic_roadmap_data as roadmap_projector
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


class RoadmapTotalsRecord(typ.TypedDict):
    """JSON-compatible aggregate generated roadmap data."""

    done: int
    total: int


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


def test_roadmap_task_macro_matches_the_representative_snapshot() -> None:
    """A fixed nested task fixture keeps the accessible roadmap markup stable."""
    environment = Environment(
        autoescape=True,
        loader=FileSystemLoader(REPO_ROOT / "templates/episodic"),
    )
    rendered = environment.from_string(
        '{% import "records.jinja" as rec %}{{ rec.roadmap_task(task) }}'
    ).render(
        task={
            "id": "7.2.1",
            "title": "Archive `sample`.",
            "done": False,
            "requires": ["1.1.1"],
            "subtasks": [
                {"title": "Keep the source.", "done": True},
                {"title": "Verify the copy.", "done": False},
            ],
        }
    )
    snapshot = (REPO_ROOT / "tests/snapshots/episodic-roadmap-task.snap").read_text(
        encoding="utf-8"
    )

    assert BeautifulSoup(rendered, "html.parser").prettify() == snapshot, (
        "the representative roadmap task macro must match its stable HTML snapshot"
    )


def _generated_roadmap_payload(
    output: Path,
) -> tuple[list[RoadmapPhaseRecord], RoadmapTotalsRecord]:
    """Render the generated Jinja declarations as JSON-compatible data."""
    environment = Environment(autoescape=True, loader=FileSystemLoader(output.parent))
    rendered = environment.from_string(
        '{% from "roadmap.jinja" import roadmap_phases, roadmap_totals %}'
        "{{ {'phases': roadmap_phases, 'totals': roadmap_totals} | tojson }}"
    ).render()
    payload = json.loads(rendered)
    return (
        typ.cast("list[RoadmapPhaseRecord]", payload["phases"]),
        typ.cast("RoadmapTotalsRecord", payload["totals"]),
    )


def test_projector_generates_and_checks_a_temporary_roadmap(tmp_path: Path) -> None:
    """The command projects structured data, checks it, and detects drift."""
    source = tmp_path / "episodic source"
    roadmap = source / "docs" / "roadmap.md"
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(
        "## 1. Foundation\n\n"
        "### 1.1. Core\n\n"
        "- [x] 1.1.1. Complete the first task.\n"
        "  - [x] Complete a nested task.\n"
        "- [ ] 1.1.2. Complete the second task. Requires 1.1.1.\n\n"
        "## 2. Delivery\n\n"
        "### 2.1. Release\n\n"
        "- [ ] 2.1.1. Prepare a release.\n"
        "  - Requires 1.1.1 and 1.1.2. Keep this note.\n"
        "- [x] 2.1.2. Publish the release.\n",
        encoding="utf-8",
    )
    output = tmp_path / "generated" / "roadmap.jinja"
    arguments = ["--episodic-root", str(source), "--output", str(output)]

    assert main(arguments) == 0, "projector must generate a missing output file"
    phases, totals = _generated_roadmap_payload(output)

    assert [phase["number"] for phase in phases] == ["1", "2"], (
        "projector output must preserve ordered phase identifiers"
    )
    assert [[step["id"] for step in phase["steps"]] for phase in phases] == [
        ["1.1"],
        ["2.1"],
    ], "projector output must preserve ordered step identifiers"
    assert [
        task["id"]
        for phase in phases
        for step in phase["steps"]
        for task in step["tasks"]
    ] == ["1.1.1", "1.1.2", "2.1.1", "2.1.2"], (
        "projector output must preserve ordered task identifiers"
    )
    assert [
        task["done"]
        for phase in phases
        for step in phase["steps"]
        for task in step["tasks"]
    ] == [True, False, False, True], (
        "projector output must preserve completed and incomplete task states"
    )
    assert [phase["state"] for phase in phases] == ["in-progress", "in-progress"], (
        "projector output must calculate phase delivery states from task completion"
    )
    task_by_id = {
        task["id"]: task
        for phase in phases
        for step in phase["steps"]
        for task in step["tasks"]
    }
    assert task_by_id["1.1.2"]["requires"] == ["1.1.1"], (
        "title dependencies must be normalized into generated requires arrays"
    )
    assert task_by_id["2.1.1"]["requires"] == ["1.1.1", "1.1.2"], (
        "first-note dependencies must be normalized into generated requires arrays"
    )
    assert task_by_id["2.1.1"]["notes"] == ["Keep this note."], (
        "first-note normalization must preserve unrelated note content"
    )
    assert totals == {"done": 2, "total": 4}, (
        "projector output must aggregate completed and total tasks across phases"
    )
    assert main([*arguments, "--check"]) == 0, (
        "projector check must accept a matching generated file"
    )

    output.write_text("stale\n", encoding="utf-8")
    assert main([*arguments, "--check"]) == 1, (
        "projector check must reject output that drifts from its source roadmap"
    )


@pytest.mark.parametrize("failure", ["write", "replace"])
def test_atomic_projector_write_preserves_output_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    """A temporary-write or replace failure keeps the prior generated file intact."""
    output = tmp_path / "roadmap.jinja"
    output.write_text("complete prior projection\n", encoding="utf-8")
    original_open = Path.open
    original_replace = Path.replace

    if failure == "write":

        class FailingTemporaryStream:
            """Close the real stream after deterministically rejecting writes."""

            def __init__(self, stream: typ.TextIO) -> None:
                self.stream = stream

            def __enter__(self) -> typ.Self:
                return self

            def __exit__(self, *_: object) -> None:
                self.stream.close()

            def write(self, _: str) -> int:
                raise OSError

        open_file = typ.cast("typ.Callable[..., typ.TextIO]", original_open)

        def fail_temporary_write(
            path: Path, *args: object, **kwargs: object
        ) -> typ.TextIO:
            stream = open_file(path, *args, **kwargs)
            if path.name.startswith(f".{output.name}."):
                return typ.cast("typ.TextIO", FailingTemporaryStream(stream))
            return stream

        monkeypatch.setattr(Path, "open", fail_temporary_write)
    else:

        def fail_replacement(path: Path, target: Path) -> Path:
            if path.name.startswith(f".{output.name}."):
                raise OSError
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", fail_replacement)

    with pytest.raises(OSError, match=r"^$"):
        roadmap_projector._write_atomically(output, "new incomplete projection\n")

    assert output.read_text(encoding="utf-8") == "complete prior projection\n", (
        "an atomic-write failure must leave the prior complete output unchanged"
    )
    assert not list(tmp_path.glob(f".{output.name}.*.tmp")), (
        "an atomic-write failure must clean up its exclusive temporary file"
    )
