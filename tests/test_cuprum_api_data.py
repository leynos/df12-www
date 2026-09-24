"""The Cuprum API reference generator: parsing, grouping, and drift checks.

``scripts/cuprum_api_parser.py`` reads a package's exports from source, and
``scripts/build_cuprum_api_data.py`` groups them into the site's reference
pages. These tests build a small package in a temporary directory, shaped like
the patterns Cuprum uses (re-exports through subpackages, a submodule export,
a ``NewType``, an alias, dataclasses, enums, properties, and overloads), and
check what the generator makes of each.
"""

from __future__ import annotations

import shutil
import string
import subprocess
import textwrap
import typing as typ

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts import build_cuprum_api_data as builder
from scripts.cuprum_api_parser import (
    SECTION_NAMES,
    ApiSourceError,
    Docstring,
    Field,
    load_api,
    parse_docstring,
)

if typ.TYPE_CHECKING:
    from pathlib import Path as PathType

PACKAGE = {
    "__init__.py": '''
        """A fixture package."""
        from pkg import sh
        from pkg.core import Colour, Settings, run
        from pkg.types import Name
        from .context import current, get_current

        __all__ = ["Colour", "Name", "Settings", "current", "get_current", "run", "sh"]
    ''',
    "types.py": """
        import typing as typ

        Name = typ.NewType("Name", str)
    """,
    "core.py": '''
        import dataclasses as dc
        import enum
        import typing as typ


        class Colour(enum.StrEnum):
            """The colours."""

            RED = "red"
            """Stop."""


        @dc.dataclass(frozen=True)
        class Settings:
            """Run settings.

            Attributes
            ----------
            depth : int
                How deep.
            """

            depth: int = 3
            label: str | None = None
            REGISTRY: typ.ClassVar[dict[str, int]] = {}

            @property
            def doubled(self) -> int:
                """Twice the depth."""
                return self.depth * 2

            @typ.overload
            def scale(self, by: int) -> int: ...
            @typ.overload
            def scale(self, by: float) -> float: ...
            def scale(self, by):
                """Scale the depth."""
                return self.depth * by

            def _private(self) -> None:
                """Not documented."""


        def run(program: str, *, timeout: float | None = None) -> int:
            """Run ``program`` and return its exit code.

            Uses :class:`Settings` for the depth.

            Parameters
            ----------
            program : str
                What to run.
            timeout : float | None
                Seconds to wait.

            Returns
            -------
            int
                The exit code.

            Raises
            ------
            TimeoutError
                If it takes too long.

            Examples
            --------
            >>> run("true")
            0
            """
            return 0
    ''',
    "context/__init__.py": """
        from .state import current, get_current

        __all__ = ["current", "get_current"]
    """,
    "context/state.py": '''
        def current() -> str:
            """Return the current context."""
            return "root"


        get_current = current
    ''',
    "sh.py": '''
        """Command construction."""

        __all__ = ["Settings", "make"]

        from pkg.core import Settings


        def make(name: str) -> str:
            """Build a command called ``name``."""
            return name
    ''',
}


def _write_package(root: PathType) -> PathType:
    """Write the fixture package under ``root`` and return ``root``."""
    for relative, source in PACKAGE.items():
        path = root / "pkg" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    return root


def _git(*args: str) -> None:
    """Run git, resolved on ``PATH``, for a fixture repository."""
    git = shutil.which("git")
    assert git is not None, "git is required to build the fixture repository"
    subprocess.run([git, *args], check=True)  # noqa: S603 - fixed argv over a temporary directory


@pytest.fixture
def api(tmp_path: PathType) -> dict[str, typ.Any]:
    """Return the fixture package's entries, keyed by exported name."""
    return {entry.name: entry for entry in load_api(_write_package(tmp_path), "pkg")}


def test_every_export_resolves_through_its_re_exports(api: dict[str, typ.Any]) -> None:
    """Names re-exported through subpackages resolve to their defining module."""
    assert set(api) == {
        "Colour",
        "Name",
        "Settings",
        "current",
        "get_current",
        "run",
        "sh",
    }
    assert api["current"].module == "pkg.context.state"
    assert api["run"].path == "pkg/core.py"


def test_kinds_distinguish_new_types_aliases_and_modules(
    api: dict[str, typ.Any],
) -> None:
    """A NewType, an alias of another export, and a submodule each say so."""
    assert api["Name"].kind == "new type"
    assert api["get_current"].kind == "alias"
    assert api["get_current"].signature == " = current"
    assert api["sh"].kind == "module"


def test_a_module_lists_only_what_the_package_does_not_re_export(
    api: dict[str, typ.Any],
) -> None:
    """``sh`` exports ``Settings`` too, but that has its own entry already."""
    assert [member.name for member in api["sh"].members] == ["make"]


def test_a_dataclass_signature_comes_from_its_fields(api: dict[str, typ.Any]) -> None:
    """Class variables are left out; defaults are kept."""
    assert api["Settings"].signature == "(depth: int = 3, label: str | None = None)"


def test_class_members_keep_public_fields_properties_and_one_overload(
    api: dict[str, typ.Any],
) -> None:
    """Private methods and overload stubs are skipped; a property is marked."""
    members = {member.name: member.kind for member in api["Settings"].members}
    assert members == {
        "depth": "field",
        "label": "field",
        "doubled": "property",
        "scale": "method",
    }


def test_enumeration_members_carry_their_docstrings(api: dict[str, typ.Any]) -> None:
    """An enum member's trailing string literal documents it."""
    (red,) = api["Colour"].members
    assert (red.name, red.kind, red.doc.summary) == ("RED", "member", "Stop.")


def test_numpy_sections_are_parsed(api: dict[str, typ.Any]) -> None:
    """Parameters, Returns, Raises, and Examples are all recovered."""
    doc = api["run"].doc
    assert doc.summary == "Run ``program`` and return its exit code."
    assert doc.body == ("Uses :class:`Settings` for the depth.",)
    assert [(f.name, f.type) for f in doc.fields["Parameters"]] == [
        ("program", "str"),
        ("timeout", "float | None"),
    ]
    assert doc.fields["Returns"][0].type == "int"
    assert doc.fields["Raises"][0].name == "TimeoutError"
    assert doc.examples == '>>> run("true")\n0'


def test_a_missing_docstring_parses_as_empty() -> None:
    """Undocumented names still render, with an empty summary."""
    assert parse_docstring(None).summary == ""


def test_a_name_imported_from_outside_the_package_is_refused(
    tmp_path: PathType,
) -> None:
    """The reference documents the package's own definitions only."""
    root = _write_package(tmp_path)
    init = root / "pkg" / "__init__.py"
    init.write_text('from os import path\n__all__ = ["path"]\n', encoding="utf-8")
    with pytest.raises(ApiSourceError, match="outside the package"):
        load_api(root, "pkg")


def test_inline_markup_becomes_code_and_links() -> None:
    """Literals and references render as code, and known names link."""
    html = builder.inline_html(
        "Use ``a < b`` with :class:`SafeCmd` or `x`.", frozenset({"SafeCmd"})
    )
    assert html == (
        'Use <code>a &lt; b</code> with <a href="#SafeCmd"><code>SafeCmd</code></a> '
        "or <code>x</code>."
    )


def test_long_declarations_are_set_one_parameter_to_a_line() -> None:
    """Annotated defaults are spaced, and a long list wraps."""
    short = builder.display_line(
        "function", "make", "(program: Program, *, catalogue: Cat=DEFAULT)"
    )
    assert short == "def make(program: Program, *, catalogue: Cat = DEFAULT)"
    long = builder.display_line(
        "class",
        "Options",
        "(" + ", ".join(f"option_{i}: int=0" for i in range(6)) + ")",
    )
    assert long.splitlines()[0] == "class Options("
    assert long.splitlines()[1] == "    option_0: int = 0,"
    assert long.splitlines()[-1] == ")"


def test_a_module_is_shown_as_its_import() -> None:
    """A module's declaration is the import that reaches it."""
    assert builder.display_line("module", "sh", "") == "from cuprum import sh"


def test_grouping_refuses_an_unplaced_or_stale_name(
    api: dict[str, typ.Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name Cuprum adds, or one it drops, stops the build."""
    monkeypatch.setattr(
        builder,
        "GROUPS",
        ({"slug": "all", "title": "All", "lede": "", "names": ("run", "gone")},),
    )
    with pytest.raises(builder.GroupingError) as excinfo:
        builder.group_entries(list(api.values()))
    message = str(excinfo.value)
    assert (
        "unplaced ['Colour', 'Name', 'Settings', 'current', 'get_current', 'sh']"
        in message
    )
    assert "no longer exported ['gone']" in message


def _pages_config(path: PathType, release: str) -> PathType:
    """Write a site configuration documenting Cuprum ``release`` at ``path``."""
    path.write_text(
        f'sites:\n  cuprum:\n    template_vars:\n      cuprum_pypi: "{release}"\n',
        encoding="utf-8",
    )
    return path


def test_check_mode_reports_drift(
    tmp_path: PathType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--check`` passes on fresh output and fails once the file differs."""
    root = _write_package(tmp_path / "src")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0"\n', encoding="utf-8"
    )
    _git("init", "-q", str(root))
    _git(
        "-C",
        str(root),
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "fixture",
    )
    monkeypatch.setattr(
        builder,
        "GROUPS",
        (
            {
                "slug": "all",
                "title": "All",
                "lede": "Everything.",
                "names": (
                    "Colour",
                    "Name",
                    "Settings",
                    "current",
                    "get_current",
                    "run",
                    "sh",
                ),
            },
        ),
    )
    monkeypatch.setattr(
        builder, "load_api", lambda path, _package, _extra=(): load_api(path, "pkg")
    )
    output = tmp_path / "api.jinja"
    pages = _pages_config(tmp_path / "pages.yaml", "1.0")
    args = [
        "--cuprum-root",
        str(root),
        "--output",
        str(output),
        "--pages-config",
        str(pages),
    ]
    assert builder.main(args) == 0
    assert "{% set api_groups = " in output.read_text(encoding="utf-8")
    assert builder.main([*args, "--check"]) == 0
    output.write_text(output.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert builder.main([*args, "--check"]) == 1
    written = output.read_text(encoding="utf-8")
    _pages_config(pages, "1.1")
    with pytest.raises(builder.ReleaseMismatchError, match=r"documents 1\.1"):
        builder.main(args)
    assert output.read_text(encoding="utf-8") == written, "a refused run wrote"


def test_an_extra_module_lists_what_the_package_does_not_export(
    tmp_path: PathType,
) -> None:
    """A public submodule outside ``__all__`` is documented by its dotted name."""
    entries = load_api(_write_package(tmp_path), "pkg", ("pkg.sh",))
    module = entries[-1]
    assert (module.name, module.kind) == ("pkg.sh", "module")
    assert [member.name for member in module.members] == ["make"]
    assert builder.display_line("module", "pkg.sh", "") == "from pkg import sh"


def test_a_bare_field_header_and_section_prose_are_told_apart() -> None:
    """``name:`` is a field; an unindented sentence is prose about the section."""
    text = "\n".join(
        [
            "Summary.",
            "",
            "Attributes",
            "----------",
            "phase:",
            "    The phase.",
            "",
            "New fields are appended at the end.",
            "",
            "Example",
            "-------",
            ">>> 1",
            "1",
        ]
    )
    doc = parse_docstring(text)
    assert [(f.name, f.description) for f in doc.fields["Attributes"]] == [
        ("phase", "The phase.")
    ]
    assert doc.texts["Attributes"] == ("New fields are appended at the end.",)
    assert doc.examples == ">>> 1\n1"


def _write_module(root: PathType, relative: str, source: str) -> None:
    """Overwrite or add ``relative`` in the fixture package under ``root``."""
    path = root / "pkg" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")


def test_a_computed_all_is_refused(tmp_path: PathType) -> None:
    """Only a literal ``__all__`` is read; a computed one cannot be trusted."""
    root = _write_package(tmp_path)
    _write_module(
        root,
        "__init__.py",
        """
        def list_of_names() -> list[str]:
            return ["run"]

        __all__ = list_of_names()
        """,
    )
    with pytest.raises(ApiSourceError, match="declares no literal __all__"):
        load_api(root, "pkg")


def test_an_extra_module_without_source_is_refused(tmp_path: PathType) -> None:
    """A configured submodule that has no file under the package stops the load."""
    root = _write_package(tmp_path)
    with pytest.raises(ApiSourceError, match=r"no source for module 'pkg\.absent'"):
        load_api(root, "pkg", ("pkg.absent",))


def test_an_import_cycle_is_reported(tmp_path: PathType) -> None:
    """Two modules that import a name from each other name the cycle."""
    root = _write_package(tmp_path)
    _write_module(root, "__init__.py", 'from .a import loop\n__all__ = ["loop"]\n')
    _write_module(root, "a.py", "from .b import loop\n")
    _write_module(root, "b.py", "from .a import loop\n")
    with pytest.raises(ApiSourceError, match="import cycle while resolving 'loop'"):
        load_api(root, "pkg")


def test_an_exported_name_with_no_definition_is_refused(tmp_path: PathType) -> None:
    """A name in ``__all__`` that nothing defines or imports stops the load."""
    root = _write_package(tmp_path)
    _write_module(root, "__init__.py", '__all__ = ["ghost"]\n')
    with pytest.raises(
        ApiSourceError, match=r"cannot find a definition of 'ghost' in pkg$"
    ):
        load_api(root, "pkg")


def test_a_missing_import_reports_the_name_not_a_submodule(
    tmp_path: PathType,
) -> None:
    """The submodule fallback does not mask why an imported name failed.

    ``from .helpers import missing`` names neither an attribute of
    ``helpers`` nor a ``helpers.missing`` submodule. The error must say the
    definition is missing, not that ``pkg.helpers.missing`` has no source.
    """
    root = _write_package(tmp_path)
    _write_module(
        root, "__init__.py", 'from .helpers import missing\n__all__ = ["missing"]\n'
    )
    _write_module(root, "helpers.py", "def present() -> None:\n    pass\n")
    with pytest.raises(
        ApiSourceError, match=r"cannot find a definition of 'missing' in pkg\.helpers"
    ) as excinfo:
        load_api(root, "pkg")
    assert "no source for module" not in str(excinfo.value)


def test_a_relative_submodule_import_resolves_to_the_module(
    tmp_path: PathType,
) -> None:
    """``from . import sh`` names a submodule and documents it as a module."""
    root = _write_package(tmp_path)
    _write_module(root, "__init__.py", 'from . import sh\n__all__ = ["sh"]\n')
    (entry,) = load_api(root, "pkg")
    assert (entry.name, entry.kind, entry.module) == ("sh", "module", "pkg.sh")
    assert entry.doc.summary == "Command construction."
    assert [member.name for member in entry.members] == ["Settings", "make"]


# Property tests: docstrings rendered from a generated layout parse back to
# that layout. The strategies stay inside what ``parse_docstring`` supports:
# field headers are ``name : type``, ``name:``, or a bare ``name`` (a bare
# type in Returns and Yields), descriptions are indented, and prose inside a
# field section is unindented, holds more than one word per line, and forms
# one block before or after the fields. Prose on both sides of a field is
# outside that contract: the parser joins the two blocks into one paragraph.

_FIELD_SECTION_NAMES = frozenset(
    {"Parameters", "Attributes", "Returns", "Yields", "Raises", "Warns"}
)
_RETURN_SECTION_NAMES = frozenset({"Returns", "Yields"})
_WORDS = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8)
_NAMES = st.tuples(
    st.sampled_from(("", "", "*", "**")),
    st.from_regex(r"[a-z_][a-z0-9_]{0,11}", fullmatch=True),
).map("".join)
_TYPES = st.sampled_from(
    (
        "int",
        "str | None",
        "list[str]",
        "tuple[int, ...]",
        "typ.Any",
        "float, optional",
        "cabc.Callable[[str], None]",
        "SafeCmd",
    )
)


@st.composite
def _paragraph(draw: st.DrawFn, *, min_words: int = 1) -> tuple[list[str], str]:
    """Draw a paragraph's source lines and the single line it parses to."""
    lines = [
        " ".join(words)
        for words in draw(
            st.lists(
                st.lists(_WORDS, min_size=min_words, max_size=6),
                min_size=1,
                max_size=3,
            )
        )
    ]
    return lines, " ".join(lines)


def _stack(blocks: list[list[str]]) -> list[str]:
    """Join blocks of lines with one blank line between each pair."""
    lines: list[str] = []
    for index, block in enumerate(blocks):
        if index:
            lines.append("")
        lines.extend(block)
    return lines


@st.composite
def _field(draw: st.DrawFn, *, returns: bool) -> tuple[list[str], Field]:
    """Draw one field entry's lines and the :class:`Field` it parses to."""
    kind = draw(_TYPES)
    paragraphs = draw(st.lists(_paragraph(), max_size=2))
    body = [f"    {line}" for line in _stack([lines for lines, _ in paragraphs])]
    description = " ".join(text for _, text in paragraphs)
    if returns and draw(st.booleans()):
        return [kind, *body], Field("", kind, description)
    name = draw(_NAMES)
    form = "typed" if returns else draw(st.sampled_from(("typed", "bare", "colon")))
    header = {"typed": f"{name} : {kind}", "bare": name, "colon": f"{name}:"}[form]
    return [header, *body], Field(name, kind if form == "typed" else "", description)


@st.composite
def _field_section(
    draw: st.DrawFn, name: str
) -> tuple[list[str], tuple[Field, ...], tuple[str, ...]]:
    """Draw a field section's content, its fields, and its prose paragraphs."""
    returns = name in _RETURN_SECTION_NAMES
    entries = draw(st.lists(_field(returns=returns), max_size=4))
    field_lines: list[str] = []
    for index, (lines, _) in enumerate(entries):
        if index and draw(st.booleans()):
            field_lines.append("")
        field_lines.extend(lines)
    prose = [] if returns else draw(st.lists(_paragraph(min_words=2), max_size=2))
    prose_lines = _stack([lines for lines, _ in prose])
    blocks = [block for block in (field_lines, prose_lines) if block]
    if draw(st.booleans()):
        blocks.reverse()
    fields = tuple(field for _, field in entries)
    return _stack(blocks), fields, tuple(text for _, text in prose)


@st.composite
def _examples(draw: st.DrawFn) -> list[str]:
    """Draw doctest lines for an Examples section."""
    pairs = draw(st.lists(st.tuples(_WORDS, _WORDS), min_size=1, max_size=3))
    return [line for source, result in pairs for line in (f">>> {source}", result)]


@st.composite
def _docstrings(draw: st.DrawFn) -> tuple[str, Docstring]:
    """Draw a NumPy-style docstring and the :class:`Docstring` it describes."""
    summary_lines, summary = draw(_paragraph())
    body = draw(st.lists(_paragraph(), max_size=3))
    names = draw(st.lists(st.sampled_from(SECTION_NAMES), unique=True))
    blocks = [summary_lines, *(lines for lines, _ in body)]
    fields: dict[str, tuple[Field, ...]] = {}
    texts: dict[str, tuple[str, ...]] = {}
    examples = ""
    for name in names:
        heading = name
        if name in _FIELD_SECTION_NAMES:
            content, fields[name], prose = draw(_field_section(name))
            if prose:
                texts[name] = prose
        elif name == "Examples":
            heading = draw(st.sampled_from(("Examples", "Example")))
            content = draw(_examples())
            examples = "\n".join(content)
        else:
            paragraphs = draw(st.lists(_paragraph(), min_size=1, max_size=3))
            content = _stack([lines for lines, _ in paragraphs])
            texts[name] = tuple(text for _, text in paragraphs)
        blocks.append([heading, "-" * len(heading), *content])
    body_texts = tuple(text for _, text in body)
    expected = Docstring(summary, body_texts, fields, texts, examples)
    return "\n".join(_stack(blocks)), expected


@settings(deadline=None)
@given(case=_docstrings())
def test_generated_numpy_docstrings_parse_to_their_layout(
    case: tuple[str, Docstring],
) -> None:
    """Sections, field names and types, and prose paragraphs are all recovered.

    Each generated docstring is rendered from a known layout, so the parse
    must reproduce that layout exactly: the summary and body paragraphs, a
    field tuple for every field section present, prose kept apart from the
    fields around it, and the Examples block as literal text.
    """
    text, expected = case
    assert parse_docstring(text) == expected, text


_COMMIT = "a" * 40


def test_a_hyphenated_pre_release_matches_its_normalized_spelling() -> None:
    """``0.2.0-beta1`` in ``pyproject.toml`` is PyPI's ``0.2.0b1``."""
    builder.check_release({"version": "0.2.0-beta1", "commit": _COMMIT}, "0.2.0b1")


def test_a_different_release_is_refused_naming_both_versions() -> None:
    """The error says which release the checkout is and which the site wants."""
    with pytest.raises(builder.ReleaseMismatchError) as excinfo:
        builder.check_release({"version": "0.2.0-beta1", "commit": _COMMIT}, "0.2.0b2")
    message = str(excinfo.value)
    assert "0.2.0-beta1" in message
    assert "but the site documents 0.2.0b2" in message


def test_an_invalid_release_cannot_be_compared() -> None:
    """A version PEP 440 cannot read is refused rather than compared as text."""
    with pytest.raises(
        builder.ReleaseMismatchError, match="cannot compare Cuprum versions"
    ):
        builder.check_release({"version": "0.2.0-beta1", "commit": _COMMIT}, "banana")


def test_the_documented_release_is_read_from_the_site_config(
    tmp_path: PathType,
) -> None:
    """``cuprum_pypi`` under the Cuprum sub-site's template variables is used."""
    pages = _pages_config(tmp_path / "pages.yaml", "0.2.0b1")
    assert builder.documented_release(pages) == "0.2.0b1"


def test_a_site_config_without_a_release_is_refused(tmp_path: PathType) -> None:
    """A config that names no Cuprum release stops the build."""
    pages = tmp_path / "pages.yaml"
    pages.write_text("sites:\n  cuprum:\n    template_vars: {}\n", encoding="utf-8")
    with pytest.raises(
        builder.ReleaseMismatchError,
        match=r"names no sites\.cuprum\.template_vars\.cuprum_pypi",
    ):
        builder.documented_release(pages)


_RELEASES = st.tuples(
    st.integers(min_value=0, max_value=30),
    st.integers(min_value=0, max_value=30),
    st.integers(min_value=0, max_value=30),
    st.integers(min_value=0, max_value=9),
)


@given(checkout=_RELEASES, documented=_RELEASES)
def test_release_spellings_compare_by_number(
    checkout: tuple[int, int, int, int], documented: tuple[int, int, int, int]
) -> None:
    """``X.Y.Z-betaN`` matches ``X.Y.ZbN`` exactly when the numbers agree."""
    major, minor, patch, beta = checkout
    identity = {"version": f"{major}.{minor}.{patch}-beta{beta}", "commit": _COMMIT}
    major, minor, patch, beta = documented
    release = f"{major}.{minor}.{patch}b{beta}"
    if checkout == documented:
        builder.check_release(identity, release)
    else:
        with pytest.raises(builder.ReleaseMismatchError, match="but the site"):
            builder.check_release(identity, release)
