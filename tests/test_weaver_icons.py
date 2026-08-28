"""The generated icon macro, and the generator that writes it.

``templates/weaver/_icons.jinja`` is generated from ``config/weaver-icons.yaml``
and the ``@iconify-json/carbon`` package. Comparing it against its generator
proves the two agree and nothing more — both could agree on markup Jinja
refuses to parse — so it is also rendered, and every icon the templates ask
for is resolved through it.
"""

from __future__ import annotations

import importlib.util
import re
import typing as typ
from pathlib import Path

import jinja2
import pytest

if typ.TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"
WEAVER_STYLES = REPO_ROOT / "src" / "styles"
COMPILED_STYLESHEET = PUBLIC_WEAVER / "assets" / "styles" / "weaver.css"


# `{{ icon('name') }}` as the templates write it, in either quote form.
ICON_CALL = re.compile(r"""icon\(\s*(?:'([^']+)'|"([^"]+)")""")


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    """Load the icon generator, which is a script rather than an importable module."""
    spec = importlib.util.spec_from_file_location(
        "generate_weaver_icons", REPO_ROOT / "scripts" / "generate_weaver_icons.py"
    )
    assert spec is not None, "scripts/generate_weaver_icons.py could not be located"
    assert spec.loader is not None, (
        "spec for generate_weaver_icons has no loader; it cannot be executed"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_icon_macro_matches_its_source(generator: ModuleType) -> None:
    """The committed icon macro should be what the generator produces.

    ``templates/weaver/_icons.jinja`` is generated from
    ``config/weaver-icons.yaml`` and the ``@iconify-json/carbon`` package. A
    hand-edit there, or a mapping change without a regeneration, would survive
    unnoticed otherwise.
    """
    if not generator.CARBON.is_file():  # pragma: no cover - environment guard
        pytest.skip("@iconify-json/carbon is not installed; run 'bun install'")

    expected = generator.build_macro()
    actual = generator.OUTPUT.read_text(encoding="utf-8")
    assert actual == expected, (
        "templates/weaver/_icons.jinja is out of date; run "
        "'uv run python scripts/generate_weaver_icons.py'"
    )


def test_the_icon_macro_renders_from_data_without_reading_a_file(
    generator: ModuleType,
) -> None:
    """The rendering is pure, so a handful of literal icons is enough to check it."""
    macro = generator.render_macro(
        {
            "terminal": {"body": "<path d='M0 0'/>"},
            "star": {"body": "<path d='M1 1'/>"},
        },
        {"asterisk": {"parent": "star"}},
        {
            "fa-terminal": {"carbon": "carbon:terminal"},
            "fa-star": {"carbon": "carbon:asterisk"},
        },
    )

    assert "'terminal': '<path d=\\'M0 0\\'/>'" in macro, (
        f"the mapped icon should carry its escaped body; got {macro!r}"
    )
    assert "'star': '<path d=\\'M1 1\\'/>'" in macro, (
        f"an alias should resolve to its parent's body; got {macro!r}"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(("{ not json", None, "malformed"), id="carbon-malformed"),
        pytest.param(('{"aliases": {}}', None, "'icons'"), id="carbon-no-icons"),
        pytest.param((None, "icons: [1, 2]", "'icons'"), id="mapping-not-a-mapping"),
        pytest.param(
            (None, "not: a mapping of icons", "'icons'"), id="mapping-no-icons"
        ),
        # The nested records are somebody else's format too, and a scalar where
        # a record was expected raises TypeError rather than KeyError — which
        # `build_macro`'s handler does not catch.
        pytest.param(
            ('{"icons": {"terminal": 5}}', None, "'body'"), id="carbon-icon-scalar"
        ),
        pytest.param(
            ('{"icons": {"terminal": {"width": 32}}}', None, "'body'"),
            id="carbon-icon-no-body",
        ),
        pytest.param(
            ('{"icons": {"terminal": {"body": 7}}}', None, "'body'"),
            id="carbon-icon-body-not-a-string",
        ),
        pytest.param(
            ('{"icons": {}, "aliases": {"star": "asterisk"}}', None, "'parent'"),
            id="carbon-alias-scalar",
        ),
        pytest.param(
            ('{"icons": {}, "aliases": {"star": {"rotate": 1}}}', None, "'parent'"),
            id="carbon-alias-no-parent",
        ),
        pytest.param(
            ('{"icons": {}, "aliases": [1, 2]}', None, "'aliases'"),
            id="carbon-aliases-not-a-mapping",
        ),
        pytest.param(
            (None, "icons:\n  fa-ghost: 5\n", "'carbon'"), id="mapping-record-scalar"
        ),
        pytest.param(
            (None, "icons:\n  fa-ghost:\n    note: no carbon here\n", "'carbon'"),
            id="mapping-record-no-carbon",
        ),
        pytest.param(
            (None, "icons:\n  fa-ghost:\n    carbon: [a, b]\n", "'carbon'"),
            id="mapping-carbon-not-a-string",
        ),
    ],
)
def test_an_unusable_generator_input_names_the_file(
    generator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: tuple[str | None, str | None, str],
) -> None:
    """A traceback out of json or ruamel names neither the file nor the fix."""
    carbon, mapping, expected = case
    carbon_path = tmp_path / "icons.json"
    carbon_path.write_text(carbon or '{"icons": {}}', encoding="utf-8")
    mapping_path = tmp_path / "weaver-icons.yaml"
    mapping_path.write_text(mapping or "icons: {}", encoding="utf-8")
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)

    with pytest.raises(SystemExit) as caught:
        generator.build_macro()

    message = str(caught.value.code)
    at_fault = carbon_path if carbon is not None else mapping_path
    assert str(at_fault) in message, (
        f"the message should name {at_fault}; got {message!r}"
    )
    assert expected in message, f"expected {expected!r} in {message!r}"


def test_an_absent_carbon_package_names_the_command_that_installs_it(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The one failure with a known fix should say what the fix is."""
    monkeypatch.setattr(generator, "CARBON", tmp_path / "absent.json")

    with pytest.raises(SystemExit) as caught:
        generator.build_macro()

    assert "bun install" in str(caught.value.code), (
        f"the message should name the fix; got {caught.value.code!r}"
    )


def test_an_unmapped_carbon_icon_names_the_mapping(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A mapping naming an icon the package lacks is an editing mistake, not a crash."""
    carbon_path = tmp_path / "icons.json"
    carbon_path.write_text('{"icons": {"terminal": {"body": ""}}}', encoding="utf-8")
    mapping_path = tmp_path / "weaver-icons.yaml"
    mapping_path.write_text(
        "icons:\n  fa-ghost:\n    carbon: carbon:no-such-icon\n", encoding="utf-8"
    )
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)

    with pytest.raises(SystemExit) as caught:
        generator.build_macro()

    message = str(caught.value.code)
    assert str(mapping_path) in message, (
        f"the message should name the mapping; got {message!r}"
    )
    assert "no-such-icon" in message, f"expected the icon named in {message!r}"


def _minimal_inputs(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, root: Path
) -> None:
    """Point the generator at a pair of valid inputs that render an empty macro."""
    carbon_path = root / "icons.json"
    carbon_path.write_text('{"icons": {}}', encoding="utf-8")
    mapping_path = root / "weaver-icons.yaml"
    mapping_path.write_text("icons: {}", encoding="utf-8")
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)


class _UnwritablePath(Path):
    """A path that reads like any other and refuses every write.

    ``main`` reads ``OUTPUT`` before it writes it, so the write handler is only
    reachable through something that lets the read succeed. Pointing ``OUTPUT``
    at a directory does not do that: ``Path.exists()`` is true for one and
    ``read_text()`` raises ``IsADirectoryError``, so the *read* handler fires
    and the write handler is never entered at all.
    """

    def write_text(self, *_args: object, **_kwargs: object) -> int:
        """Fail the way a read-only tree or a full disk would."""
        message = f"Permission denied: {self}"
        raise PermissionError(message)


def test_an_unwritable_output_reports_the_path_rather_than_an_oserror(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`main` is the CLI boundary, so its filesystem failures exit with a message."""
    _minimal_inputs(generator, monkeypatch, tmp_path)

    output = _UnwritablePath(tmp_path / "_icons.jinja")
    # Existing and readable, and holding something other than what the
    # generator will produce, so `main` gets past its unchanged short-circuit
    # and reaches the write.
    Path(output).write_text("stale", encoding="utf-8")
    monkeypatch.setattr(generator, "OUTPUT", output)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert "could not be written" in message, (
        f"the write handler should be the one that fired; got {message!r}"
    )


def test_an_unreadable_output_is_reported_separately(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The read and the write are distinct failures and say so distinctly."""
    _minimal_inputs(generator, monkeypatch, tmp_path)

    # A directory exists and cannot be read as text, which is the read handler's
    # case and not the write handler's.
    output = tmp_path / "_icons.jinja"
    output.mkdir()
    monkeypatch.setattr(generator, "OUTPUT", output)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert "could not be read" in message, (
        f"the read handler should be the one that fired; got {message!r}"
    )


@pytest.fixture(scope="module")
def icon_macro() -> typ.Callable[..., str]:
    """Load `_icons.jinja` through Jinja and return its `icon` macro.

    The generated file is compared against the generator elsewhere, which
    proves the two agree and nothing more: both could agree on markup Jinja
    refuses to parse, or on a macro that renders an empty string. Rendering it
    is what shows it works.
    """
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(WEAVER_TEMPLATES)),
        autoescape=True,
    )
    module = environment.get_template("_icons.jinja").module
    # The macro is an attribute of the rendered module, which is dynamic, so
    # the type checker cannot see it; that it exists at all is the first thing
    # these tests assert.
    macro = getattr(module, "icon", None)
    assert macro is not None, (
        "templates/weaver/_icons.jinja defines no `icon` macro; every call "
        "site in every Weaver template would render nothing"
    )
    return typ.cast("typ.Callable[..., str]", macro)


def test_the_generated_macro_renders_an_svg(icon_macro: typ.Callable[..., str]) -> None:
    """A macro that parses but renders nothing would pass every other check."""
    rendered = str(icon_macro("terminal"))

    assert rendered.startswith("<svg "), f"expected an <svg> element; got {rendered!r}"
    assert 'viewBox="0 0 32 32"' in rendered, f"no viewBox in {rendered!r}"
    assert 'aria-hidden="true"' in rendered, (
        f"the artwork is decorative and must be hidden from assistive "
        f"technology; got {rendered!r}"
    )
    assert "<path" in rendered or "<circle" in rendered, (
        f"the icon rendered no artwork at all: {rendered!r}"
    )


def test_the_generated_macro_carries_extra_classes(
    icon_macro: typ.Callable[..., str],
) -> None:
    """`extra_class` is how a call site sizes or colours one instance."""
    rendered = str(icon_macro("terminal", extra_class="text-accent-ink w-6"))

    assert "text-accent-ink w-6" in rendered, (
        f"the per-instance classes were dropped: {rendered!r}"
    )
    assert "inline-block" in rendered, (
        f"the macro's own classes should survive alongside them: {rendered!r}"
    )


def test_an_unmapped_icon_name_is_loud_rather_than_blank(
    icon_macro: typ.Callable[..., str],
) -> None:
    """A missing icon that rendered nothing would leave a hole nobody noticed."""
    rendered = str(icon_macro("definitely-not-an-icon"))

    assert "UNKNOWN ICON" in rendered, (
        f"an unmapped name should say so rather than render empty; got {rendered!r}"
    )
    assert "definitely-not-an-icon" in rendered, (
        f"the message should name the icon asked for; got {rendered!r}"
    )


def test_every_icon_the_templates_ask_for_renders(
    icon_macro: typ.Callable[..., str],
) -> None:
    """A template naming an icon the macro lacks ships `UNKNOWN ICON` to a page.

    The browser suite catches this on the four pages it loads at a time; this
    catches it across every template, without a browser.
    """
    asked = {
        match.group(1) or match.group(2)
        for source in WEAVER_TEMPLATES.rglob("*.jinja")
        if source.name != "_icons.jinja"
        for match in ICON_CALL.finditer(source.read_text(encoding="utf-8"))
    }
    assert asked, "no icon calls were found at all; has the call syntax changed?"

    missing = sorted(name for name in asked if "UNKNOWN ICON" in str(icon_macro(name)))
    assert not missing, (
        f"these icons are used in the templates but absent from the generated "
        f"macro, so each renders the literal text 'UNKNOWN ICON': {missing}"
    )
