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
import subprocess
import textwrap
import typing as typ

import pytest

from scripts import build_cuprum_api_data as builder
from scripts.cuprum_api_parser import ApiSourceError, load_api, parse_docstring

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
    args = ["--cuprum-root", str(root), "--output", str(output)]
    assert builder.main(args) == 0
    assert "{% set api_groups = " in output.read_text(encoding="utf-8")
    assert builder.main([*args, "--check"]) == 0
    output.write_text(output.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert builder.main([*args, "--check"]) == 1


def test_an_extra_module_lists_what_the_package_does_not_export(
    tmp_path: PathType,
) -> None:
    """A public submodule outside ``__all__`` is documented by its dotted name."""
    entries = load_api(_write_package(tmp_path), "pkg", ("pkg.sh",))
    module = entries[-1]
    assert (module.name, module.kind) == ("pkg.sh", "module")
    assert [member.name for member in module.members] == ["make"]
    assert builder.display_line("module", "pkg.sh", "") == "from pkg import sh"
