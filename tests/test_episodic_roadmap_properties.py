"""Property tests for Episodic roadmap normalization and completion invariants."""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from scripts.episodic_roadmap_parser import parse_roadmap

LABELS = st.text(alphabet=string.ascii_letters, min_size=1, max_size=24)
DEPENDENCY_CASES = st.tuples(
    st.booleans(),
    st.booleans(),
    st.integers(min_value=1, max_value=8),
    LABELS,
    st.lists(st.booleans(), max_size=4),
    st.integers(min_value=1, max_value=8),
)


@given(case=DEPENDENCY_CASES)
def test_dependency_sentences_preserve_unrelated_task_content(
    case: tuple[bool, bool, int, str, list[bool], int],
) -> None:
    """Dependency sentences normalize without changing task state or prose."""
    completed, dependency_in_note, end, label, nested_states, start = case
    lower, upper = sorted((start, end))
    dependencies = f"1.1.{lower}-1.1.{upper}"
    checkbox = "x" if completed else " "
    title = f"Preserve {label}."
    note = ""
    if dependency_in_note:
        note = f"  - Requires {dependencies}. Keep {label} note.\n"
    else:
        title = f"{title} Requires {dependencies}."
    subtasks = "".join(
        f"  - [{'x' if state else ' '}] Preserve nested {position}.\n"
        for position, state in enumerate(nested_states, start=1)
    )
    roadmap = (
        "## 1. Phase\n\n"
        "### 1.1. Step\n\n"
        f"- [{checkbox}] 1.1.9. {title}\n"
        f"{note}{subtasks}"
    )

    phase = parse_roadmap(roadmap)[0]
    task = phase.steps[0].tasks[0]

    assert task.requires == [f"1.1.{number}" for number in range(lower, upper + 1)], (
        "dependency ranges must expand to every task identifier in source order"
    )
    assert task.done is completed, (
        "dependency normalization must preserve task completion"
    )
    assert task.title == f"Preserve {label}.", (
        "title normalization must preserve all content outside the dependency sentence"
    )
    expected_notes = [f"Keep {label} note."] if dependency_in_note else []
    assert task.notes == expected_notes, (
        "first-note normalization must preserve only unrelated note content"
    )
    assert [subtask.done for subtask in task.subtasks] == nested_states, (
        "nested task completion states must survive dependency normalization"
    )
    assert phase.total_count == 1, "nested tasks must not alter parent-task totals"
    assert phase.done_count == int(completed), (
        "nested tasks must not alter parent-task completed totals"
    )


@given(task_states=st.lists(st.booleans(), min_size=1, max_size=8))
def test_phase_totals_follow_generated_task_completion_states(
    task_states: list[bool],
) -> None:
    """Every parsed phase reports totals and delivery state from its task list."""
    tasks = "".join(
        f"- [{'x' if completed else ' '}] 1.1.{position}. Task {position}.\n"
        for position, completed in enumerate(task_states, start=1)
    )

    phase = parse_roadmap(f"## 1. Phase\n\n### 1.1. Step\n\n{tasks}")[0]

    assert phase.total_count == len(task_states), (
        "phase totals must count every generated parent task exactly once"
    )
    assert phase.done_count == sum(task_states), (
        "phase completed totals must equal the generated completed task count"
    )
    expected_state = (
        "available"
        if all(task_states)
        else "in-progress"
        if any(task_states)
        else "planned"
    )
    assert phase.state == expected_state, (
        "phase delivery state must be derived from generated task completion"
    )
