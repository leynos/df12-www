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
    """A nested checkbox beneath a roadmap task.

    Attributes
    ----------
    title : str
        Flattened subtask label from the upstream roadmap.
    done : bool
        Whether its source checkbox is complete.
    """

    title: str
    done: bool


@dc.dataclass(slots=True)
class Task:
    """One execution unit within a roadmap step.

    Attributes
    ----------
    id : str
        Dotted task identifier from the roadmap.
    title : str
        Task title after dependency-sentence normalization.
    done : bool
        Whether its source checkbox is complete.
    requires : list[str]
        Dependency task identifiers extracted from the title or first note.
    notes : list[str]
        Remaining explanatory task notes.
    subtasks : list[Subtask]
        Nested checkbox items associated with this task.
    completed_on : str
        Completion date from a structured completion note, when present.
    completion_note : str
        Completion detail from a structured completion note, when present.
    """

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
    """A workstream grouping related tasks.

    Attributes
    ----------
    id : str
        Dotted step identifier from the roadmap.
    title : str
        Step heading.
    anchor : str
        GitHub-compatible fragment for the heading.
    summary : str
        Introductory prose belonging to the step.
    tasks : list[Task]
        Tasks ordered as they occur in the source.
    """

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
    """A strategic delivery milestone.

    Attributes
    ----------
    number : str
        Top-level phase number from the roadmap.
    title : str
        Phase heading.
    anchor : str
        GitHub-compatible fragment for the heading.
    summary : str
        Introductory prose belonging to the phase.
    steps : list[Step]
        Workstreams ordered as they occur in the source.
    """

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
    """Return the GitHub heading anchor for ``heading``.

    Parameters
    ----------
    heading : str
        Heading text without its leading Markdown hashes.

    Returns
    -------
    str
        Fragment identifier with links and inline code reduced to their text.
    """
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


@dc.dataclass(slots=True)
class _ParserState:
    """Mutable source-order state for the one-pass Markdown parser."""

    phases: list[Phase] = dc.field(default_factory=list)
    step: Step | None = None
    task: Task | None = None
    notes: list[str] = dc.field(default_factory=list)
    summary: list[str] = dc.field(default_factory=list)


def _close_task(state: _ParserState) -> None:
    """Attach buffered notes and clear the current task."""
    if state.task is not None:
        _finish_task(state.task, state.notes)
    state.task = None
    state.notes = []


def _summary_target(state: _ParserState) -> Phase | Step | None:
    """Return the open step, or otherwise the most recent phase."""
    return state.step or (state.phases[-1] if state.phases else None)


def _close_summary(state: _ParserState) -> None:
    """Attach buffered prose to the current phase or step."""
    target = _summary_target(state)
    if target is not None and not target.summary and state.summary:
        target.summary = _strip_cross_references(_flatten(" ".join(state.summary)))
    state.summary = []


def _close_open_records(state: _ParserState) -> None:
    """Finish any task and summary preceding a structural Markdown item."""
    _close_task(state)
    _close_summary(state)


def _start_phase(state: _ParserState, match: re.Match[str]) -> None:
    """Start a phase after finalizing preceding source-order state."""
    _close_open_records(state)
    state.step = None
    title = _flatten(match.group(2))
    state.phases.append(
        Phase(
            number=match.group(1),
            title=title,
            anchor=slugify(f"{match.group(1)}. {title}"),
        )
    )


def _start_step(state: _ParserState, match: re.Match[str]) -> None:
    """Start a step and attach it to the current phase when available."""
    _close_open_records(state)
    title = _flatten(match.group(2))
    state.step = Step(
        id=match.group(1),
        title=title,
        anchor=slugify(f"{match.group(1)}. {title}"),
    )
    if state.phases:
        state.phases[-1].steps.append(state.step)


def _start_task(state: _ParserState, match: re.Match[str]) -> None:
    """Start a task and attach it to the current step when available."""
    _close_open_records(state)
    state.task = Task(
        id=match.group(2),
        title=match.group(3).strip(),
        done=match.group(1) == "x",
    )
    if state.step is not None:
        state.step.tasks.append(state.task)


def _handle_task_detail(state: _ParserState, line: str) -> bool:
    """Consume one task-owned source line and report whether it was claimed."""
    if state.task is None:
        return False
    if sub_match := SUBTASK_ITEM.match(line):
        state.task.subtasks.append(
            Subtask(title=_flatten(sub_match.group(2)), done=sub_match.group(1) == "x")
        )
    elif note_match := NOTE_ITEM.match(line):
        state.notes.append(note_match.group(1))
    elif state.notes and (cont_match := NOTE_CONTINUATION.match(line)):
        state.notes[-1] = f"{state.notes[-1]} {cont_match.group(1)}"
    elif not state.notes and (cont_match := TITLE_CONTINUATION.match(line)):
        state.task.title = f"{state.task.title} {cont_match.group(1).strip()}"
    elif not line.strip():
        pass
    else:
        _close_task(state)
    return True


def parse_roadmap(text: str) -> list[Phase]:
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
    state = _ParserState()

    for line in text.splitlines():
        if phase_match := PHASE_HEADING.match(line):
            _start_phase(state, phase_match)
            continue

        if step_match := STEP_HEADING.match(line):
            _start_step(state, step_match)
            continue

        if task_match := TASK_ITEM.match(line):
            _start_task(state, task_match)
            continue

        if _handle_task_detail(state, line):
            continue

        if line.strip() and not line.startswith(("#", "-", "[", "|", "```")):
            state.summary.append(line.strip())

    _close_open_records(state)

    for phase in state.phases:
        for phase_step in phase.steps:
            for phase_task in phase_step.tasks:
                _extract_requirements(phase_task)
    return state.phases


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
    """Parse the roadmap Markdown at ``path``.

    Parameters
    ----------
    path : pathlib.Path
        Authoritative Episodic roadmap Markdown file.

    Returns
    -------
    list[Phase]
        Ordered phase records with normalized task dependencies.
    """
    return parse_roadmap(path.read_text(encoding="utf-8"))
