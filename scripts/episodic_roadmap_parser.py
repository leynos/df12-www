"""Parse the upstream Episodic roadmap into structured phase records.

The upstream ``docs/roadmap.md`` is authoritative for delivery state. This
module reads that Markdown and returns phases, steps, and tasks with their
checkbox state, dependencies, completion notes, and heading anchors, so the
site never maintains a second set of completion states.
"""

from __future__ import annotations

import dataclasses as dc
import re
import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path

PHASE_HEADING = re.compile(r"^## (\d+)\.\s+(.*)$")
STEP_HEADING = re.compile(r"^### (\d+\.\d+)\.\s+(.*)$")
TASK_ITEM = re.compile(r"^- \[( |x)\] (\d+\.\d+\.\d+)\.\s+(.*)$")
SUBTASK_ITEM = re.compile(r"^ {2}- \[( |x)\]\s+(.*)$")
NOTE_ITEM = re.compile(r"^ {2}- (?!\[[ x]\])(.*)$")
NOTE_CONTINUATION = re.compile(r"^ {4,}(?![-*] )(\S.*)$")
TITLE_CONTINUATION = re.compile(r"^ {2}(?![-*] )(\S.*)$")
TASK_ID = r"\d+\.\d+\.\d+"
DEPENDENCY_TOKEN = rf"{TASK_ID}(?:-{TASK_ID})?"
DEPENDENCY_SEPARATOR = r"(?:,\s*(?:and\s+)?|\s+and\s+)"
REQUIRES_SENTENCE = re.compile(
    rf"(?<!\S)Requires (?P<dependencies>{DEPENDENCY_TOKEN}"
    rf"(?:{DEPENDENCY_SEPARATOR}{DEPENDENCY_TOKEN})*)\.(?:\s+|$)"
)
DEPENDENCY = re.compile(rf"(?P<start>{TASK_ID})(?:-(?P<end>{TASK_ID}))?")
COMPLETED_NOTE = re.compile(r"^Completed (\d{4}-\d{2}-\d{2}):\s*(.*)$", re.DOTALL)
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
INLINE_CODE = re.compile(r"`([^`]+)`")


@dc.dataclass(slots=True)
class Subtask:
    """A nested checkbox beneath a roadmap task."""

    title: str
    done: bool


@dc.dataclass(slots=True)
class Task:
    """One execution unit within a roadmap step."""

    id: str
    title: str
    done: bool
    requires: list[str] = dc.field(default_factory=list)
    notes: list[str] = dc.field(default_factory=list)
    subtasks: list[Subtask] = dc.field(default_factory=list)
    completed_on: str = ""
    completion_note: str = ""


@dc.dataclass(slots=True)
class Step:
    """A workstream grouping related tasks."""

    id: str
    title: str
    anchor: str
    summary: str = ""
    tasks: list[Task] = dc.field(default_factory=list)

    @property
    def done_count(self) -> int:
        """Return the number of completed tasks in this step."""
        return sum(1 for task in self.tasks if task.done)


@dc.dataclass(slots=True)
class Phase:
    """A strategic delivery milestone."""

    number: str
    title: str
    anchor: str
    summary: str = ""
    steps: list[Step] = dc.field(default_factory=list)

    @property
    def tasks(self) -> list[Task]:
        """Return every task across this phase's steps."""
        return [task for step in self.steps for task in step.tasks]

    @property
    def done_count(self) -> int:
        """Return the number of completed tasks in this phase."""
        return sum(1 for task in self.tasks if task.done)

    @property
    def total_count(self) -> int:
        """Return the total number of tasks in this phase."""
        return len(self.tasks)

    @property
    def state(self) -> str:
        """Return ``available``, ``in-progress``, or ``planned``."""
        if self.total_count and self.done_count == self.total_count:
            return "available"
        return "in-progress" if self.done_count else "planned"


def slugify(heading: str) -> str:
    """Return the GitHub heading anchor for ``heading``."""
    text = LINK.sub(r"\1", heading)
    text = INLINE_CODE.sub(r"\1", text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_]+", "-", text.strip())


def _flatten(text: str) -> str:
    """Collapse Markdown links, code spans, and wrapped whitespace."""
    text = LINK.sub(r"\1", text)
    text = INLINE_CODE.sub(r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


SENTENCE_SPLIT = re.compile(r"(?<=[.:])\s+")


def _strip_cross_references(text: str) -> str:
    """Remove trailing ``See ...`` pointers left behind by link stripping."""
    sentences = SENTENCE_SPLIT.split(text)
    while sentences and sentences[-1].lower().startswith("see "):
        sentences.pop()
    return " ".join(sentences).strip()


def _finish_task(task: Task, buffer: list[str]) -> None:
    """Attach the accumulated note buffer to ``task``."""
    for raw in buffer:
        note = _flatten(raw)
        if not note or note.startswith("See "):
            continue
        completed = COMPLETED_NOTE.match(note)
        if completed:
            task.completed_on = completed.group(1)
            task.completion_note = completed.group(2).strip()
            continue
        task.notes.append(note)


def parse_roadmap(  # noqa: PLR0912, PLR0915 - A one-pass parser keeps Markdown state local.
    text: str,
) -> list[Phase]:
    """Parse roadmap Markdown into phase records.

    Parameters
    ----------
    text : str
        Contents of the authoritative upstream ``docs/roadmap.md``.

    Returns
    -------
    list[Phase]
        Ordered phases with their steps and tasks.
    """
    phases: list[Phase] = []
    step: Step | None = None
    task: Task | None = None
    notes: list[str] = []
    summary: list[str] = []

    def close_task() -> None:
        nonlocal task, notes
        if task is not None:
            _finish_task(task, notes)
        task, notes = None, []

    def close_summary(target: Phase | Step | None) -> None:
        nonlocal summary
        if target is not None and not target.summary and summary:
            target.summary = _strip_cross_references(_flatten(" ".join(summary)))
        summary = []

    for line in text.splitlines():
        if phase_match := PHASE_HEADING.match(line):
            close_task()
            close_summary(step or (phases[-1] if phases else None))
            step = None
            title = _flatten(phase_match.group(2))
            phases.append(
                Phase(
                    number=phase_match.group(1),
                    title=title,
                    anchor=slugify(f"{phase_match.group(1)}. {title}"),
                )
            )
            continue

        if step_match := STEP_HEADING.match(line):
            close_task()
            close_summary(step or (phases[-1] if phases else None))
            title = _flatten(step_match.group(2))
            step = Step(
                id=step_match.group(1),
                title=title,
                anchor=slugify(f"{step_match.group(1)}. {title}"),
            )
            if phases:
                phases[-1].steps.append(step)
            continue

        if task_match := TASK_ITEM.match(line):
            close_task()
            close_summary(step or (phases[-1] if phases else None))
            task = Task(
                id=task_match.group(2),
                title=task_match.group(3).strip(),
                done=task_match.group(1) == "x",
            )
            if step is not None:
                step.tasks.append(task)
            continue

        if task is not None:
            if sub_match := SUBTASK_ITEM.match(line):
                task.subtasks.append(
                    Subtask(
                        title=_flatten(sub_match.group(2)),
                        done=sub_match.group(1) == "x",
                    )
                )
                continue
            if note_match := NOTE_ITEM.match(line):
                notes.append(note_match.group(1))
                continue
            if notes and (cont_match := NOTE_CONTINUATION.match(line)):
                notes[-1] = f"{notes[-1]} {cont_match.group(1)}"
                continue
            if not notes and (cont_match := TITLE_CONTINUATION.match(line)):
                task.title = f"{task.title} {cont_match.group(1).strip()}"
                continue
            if not line.strip():
                continue
            close_task()
            continue

        if line.strip() and not line.startswith(("#", "-", "[", "|", "```")):
            summary.append(line.strip())

    close_task()
    close_summary(step or (phases[-1] if phases else None))

    for phase in phases:
        for phase_step in phase.steps:
            for phase_task in phase_step.tasks:
                _extract_requirements(phase_task)
    return phases


def _extract_requirements(task: Task) -> None:
    """Move dependency sentences from a title or its first note into ``requires``."""
    title, title_requires = _remove_requirement_sentence(task.title)
    if title_requires:
        task.title = title

    note_requires: list[str] = []
    if task.notes:
        first_note, note_requires = _remove_requirement_sentence(task.notes[0])
        if note_requires:
            if first_note:
                task.notes[0] = first_note
            else:
                task.notes.pop(0)

    for requirement in [*title_requires, *note_requires]:
        if requirement not in task.requires:
            task.requires.append(requirement)


def _remove_requirement_sentence(text: str) -> tuple[str, list[str]]:
    """Remove one ``Requires`` sentence and return its expanded dependencies."""
    match = REQUIRES_SENTENCE.search(text)
    if match is None:
        return text, []
    requirements = _parse_requirements(match.group("dependencies"))
    if not requirements:
        return text, []
    remaining = f"{text[: match.start()]}{text[match.end() :]}"
    return re.sub(r"\s+", " ", remaining).strip(), requirements


def _parse_requirements(text: str) -> list[str]:
    """Expand listed task identifiers and same-step shorthand ranges."""
    requirements: list[str] = []
    for match in DEPENDENCY.finditer(text):
        start = match.group("start")
        end = match.group("end")
        if end is None:
            requirements.append(start)
            continue
        start_parts = start.split(".")
        end_parts = end.split(".")
        if start_parts[:2] != end_parts[:2]:
            requirements.extend((start, end))
            continue
        requirements.extend(
            f"{start_parts[0]}.{start_parts[1]}.{number}"
            for number in range(int(start_parts[2]), int(end_parts[2]) + 1)
        )
    return requirements


def load_roadmap(path: Path) -> list[Phase]:
    """Parse the roadmap Markdown at ``path``."""
    return parse_roadmap(path.read_text(encoding="utf-8"))
