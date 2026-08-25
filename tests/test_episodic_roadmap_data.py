"""Regression tests for the owned Episodic roadmap projector."""

from __future__ import annotations

import json
import typing as typ
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

from scripts.episodic_roadmap_parser import Task, parse_roadmap

REPO_ROOT = Path(__file__).resolve().parent.parent


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

    assert task.title == "Keep `inline code` in the title."
    assert task.requires == ["3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5"]
    assert task.notes == []


def test_first_note_dependency_sentence_preserves_the_remaining_note() -> None:
    """A leading dependency note moves into ``requires`` without losing prose."""
    task = _task_from(
        "## 4. Phase\n\n"
        "### 4.3. Step\n\n"
        "- [ ] 4.3.1. Keep this title.\n"
        "  - Requires 1.3.4, 1.4.3, and 4.1.1. Preserve this note.\n"
        "  - Keep this unrelated note.\n"
    )

    assert task.title == "Keep this title."
    assert task.requires == ["1.3.4", "1.4.3", "4.1.1"]
    assert task.notes == ["Preserve this note.", "Keep this unrelated note."]


def test_generated_dependency_fields_drive_the_roadmap_task_macro() -> None:
    """The four normalized tasks render dependency lines from ``task.requires``."""
    environment = Environment(
        autoescape=True,
        loader=FileSystemLoader(REPO_ROOT / "templates/episodic"),
    )
    roadmap_phases = typ.cast(
        "list[dict[str, typ.Any]]",
        json.loads(
            environment.from_string(
                '{% from "data/roadmap.jinja" import roadmap_phases %}'
                "{{ roadmap_phases | tojson }}"
            ).render()
        ),
    )
    tasks = {
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

    assert {task_id: tasks[task_id]["requires"] for task_id in expected} == expected
    assert all(
        "Requires " not in tasks[task_id]["title"]
        and not tasks[task_id].get("notes", [""])[0].startswith("Requires ")
        for task_id in expected
    )

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
    ]
