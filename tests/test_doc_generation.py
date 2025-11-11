"""Tests for documentation generation layout and navigation."""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import shutil
import subprocess
import typing as typ
from pathlib import Path

import msgspec.json as msgspec_json
import pytest
from bs4 import BeautifulSoup

from df12_pages.config import PageConfig, ThemeConfig
from df12_pages.generator import PageContentGenerator

REPO_ROOT = Path(__file__).resolve().parents[1]
INLINE_CODE_LABEL = "introctl"


def _require_executable(name: str) -> str:
    """Resolve an executable on PATH, raising a descriptive error if missing."""
    path = shutil.which(name)
    if not path:
        msg = f"Unable to locate '{name}' on PATH"
        raise FileNotFoundError(msg)
    return path


@pytest.fixture(scope="module")
def sample_markdown() -> str:
    """Return representative markdown with nested headings for nav tests."""
    return (
        "## 1. Introduction\n"
        "### Overview\n"
        "Intro details.\n\n"
        f"Use the `{INLINE_CODE_LABEL}` tool for bootstrapping.\n\n"
        "**Capabilities**\n"
        "Bullet list of capabilities. For more, see the [CLI reference](../cli.md#flags).\n\n"
        "### Core Philosophy:\n"
        "Why decisions matter.\n\n"
        "- **Sanitized providers** – The `sanitized_provider` helper returns a Figment\n"
        "  provider with None fields removed. It aids manual layering. For example:\n\n"
        "  ```rust,no_run\n"
        "  use figment::{Figment, providers::Serialized};\n"
        "  use ortho_config::sanitized_provider;\n\n"
        "  let fig = Figment::from(Serialized::defaults(&Defaults::default()))\n"
        "      .merge(sanitized_provider(&cli)?);\n"
        "  let cfg: Defaults = fig.extract()?;\n"
        "  ```\n\n"
        "## 2. Getting Started\n"
        "### Install\n"
        "Install steps here.\n\n"
        "### Configure\n"
        "Configuration steps here.\n"
    )


@pytest.fixture(scope="module")
def page_config(tmp_path_factory: pytest.TempPathFactory) -> PageConfig:
    """Build a minimal page configuration rooted in a temp directory."""
    output_dir = tmp_path_factory.mktemp("docs")
    theme = ThemeConfig(
        hero_eyebrow="Fixture",
        hero_tagline="Fixture tagline",
        doc_label="Docs",
        site_name="df12",
    )
    return PageConfig(
        key="test",
        label="Test Docs",
        source_url="https://example.invalid/docs.md",
        source_label="Fixture Source",
        page_title_suffix="Fixture",
        filename_prefix="docs-test-",
        output_dir=output_dir,
        pygments_style="monokai",
        footer_note="",
        theme=theme,
        layouts={},
        repo="df12/testdocs",
        branch="main",
        language=None,
        manifest_url=None,
        description_override="Fixture Description",
        doc_path="docs/users-guide.md",
        latest_release=None,
        latest_release_published_at=None,
    )


@pytest.fixture
def markdown_response(
    sample_markdown: str, monkeypatch: pytest.MonkeyPatch
) -> dict[str, typ.Any]:
    state: dict[str, typ.Any] = {
        "last_modified": "Tue, 11 Nov 2025 00:00:00 GMT",
        "calls": [],
    }

    class _Response:
        def __init__(self, body: str, headers: dict[str, str]) -> None:
            self.text = body
            self.headers = headers

        def raise_for_status(self) -> None:  # pragma: no cover - stub
            return None

    def fake_get(url: str, timeout: int = 30) -> _Response:  # noqa: ARG001
        state["calls"].append(url)
        return _Response(sample_markdown, {"Last-Modified": state["last_modified"]})

    def set_last_modified(value: str) -> None:
        state["last_modified"] = value

    state["set_last_modified"] = set_last_modified
    monkeypatch.setattr("df12_pages.generator.requests.get", fake_get)
    return state


@pytest.fixture
def generated_doc_paths(
    page_config: PageConfig,
    markdown_response: dict[str, typ.Any],  # noqa: ARG001
) -> dict[str, Path]:
    """Generate HTML pages from the sample markdown and return their paths."""
    generator = PageContentGenerator(page_config)
    written_paths = generator.run()
    return {path.name: path for path in written_paths}


@pytest.fixture
def generated_docs(generated_doc_paths: dict[str, Path]) -> dict[str, BeautifulSoup]:
    """Load generated HTML documents into BeautifulSoup trees."""
    docs: dict[str, BeautifulSoup] = {}
    for name, path in generated_doc_paths.items():
        html = path.read_text(encoding="utf-8")
        docs[name] = BeautifulSoup(html, "html.parser")
    return docs


@pytest.fixture(scope="session")
def css_build_artifact() -> Path:
    """Ensure the Tailwind/Daisy build artifact exists for tests."""
    bun_exe = _require_executable("bun")
    subprocess.run([bun_exe, "run", "build"], cwd=REPO_ROOT, check=True)  # noqa: S603
    css_path = REPO_ROOT / "public" / "assets" / "site.css"
    if not css_path.exists():  # pragma: no cover - defensive
        msg = f"Expected CSS artifact at {css_path}"
        raise FileNotFoundError(msg)
    return css_path


def test_sidebar_groups_include_top_and_child_links(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Sidebar groups should render top-level sections plus subsections."""
    soup = generated_docs["docs-test-introduction.html"]
    groups = soup.select(".doc-sidebar__groups .doc-nav-group")
    assert [g.select_one("h3").get_text(strip=True) for g in groups] == [
        "Introduction",
        "Getting Started",
    ]

    intro_links = [a.get_text(strip=True) for a in groups[0].select("a")]
    assert intro_links[0] == "Introduction"
    assert "Overview" in intro_links[1]
    assert "Capabilities" in intro_links[2]
    assert "Core Philosophy" in intro_links[3]


def test_only_one_sidebar_link_flagged_active(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Exactly one nav link should be marked as active for a page."""
    soup = generated_docs["docs-test-getting-started.html"]
    active_titles = soup.select(".doc-nav-group__title.is-active")
    assert len(active_titles) == 1


def test_bold_heading_promoted_to_nav_entry(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Standalone bold headings must surface within the contents nav."""
    soup = generated_docs["docs-test-introduction.html"]
    nav_labels = [
        span.get_text(strip=True) for span in soup.select(".doc-nav__list a span")
    ]
    assert "Capabilities" in nav_labels
    assert "Core Philosophy" in nav_labels


def test_hero_title_strips_numbering(generated_docs: dict[str, BeautifulSoup]) -> None:
    """Hero titles should omit numbering prefixes from H2 markdown."""
    soup = generated_docs["docs-test-introduction.html"]
    title_tag = soup.select_one(".doc-hero__title")
    assert title_tag is not None
    hero_title = title_tag.get_text(strip=True)
    assert hero_title == "Introduction"


def test_doc_meta_uses_source_mtime(generated_docs: dict[str, BeautifulSoup]) -> None:
    """Fallback metadata should derive from the source document mtime."""
    soup = generated_docs["docs-test-introduction.html"]
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == ["Updated Nov 11, 2025"]


def test_indented_fenced_block_renders_codehilite(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Indented fenced code blocks should render as highlighted HTML."""
    soup = generated_docs["docs-test-introduction.html"]
    code_blocks = soup.select(".doc-article .codehilite code")
    assert any("use figment" in block.get_text() for block in code_blocks)
    assert any(
        block.find_parent("div", class_="codehilite").get("data-language") == "rust"
        for block in code_blocks
    )


def test_default_layout_content_not_duplicated(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Sections without headings should render body content exactly once."""
    soup = generated_docs["docs-test-introduction.html"]
    html = soup.select_one(".doc-article").decode_contents()
    assert html.count("Sanitized providers") == 1


def test_relative_links_rewritten_to_github(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Relative links should point to the original GitHub repository blob URL."""
    soup = generated_docs["docs-test-introduction.html"]
    link = soup.select_one("a[href*='github.com']")
    assert link is not None
    assert link["href"] == "https://github.com/df12/testdocs/blob/main/cli.md#flags"


def test_sidebar_shows_label_and_description(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Sidebar should highlight the tool label and description."""
    soup = generated_docs["docs-test-introduction.html"]
    eyebrow = soup.select_one(".doc-sidebar__eyebrow")
    assert eyebrow is not None
    assert eyebrow.get_text(strip=True) == "Test Docs"
    body = soup.select_one(".doc-sidebar__body")
    assert body is not None
    assert body.get_text(strip=True) == "Fixture Description"


def _extract_nodes_by_tag(
    tree: dict[str, typ.Any], tag: str
) -> list[dict[str, typ.Any]]:
    matches: list[dict[str, typ.Any]] = []
    stack: list[dict[str, typ.Any]] = [tree]
    while stack:
        node = stack.pop()
        if node.get("tag") == tag:
            matches.append(node)
        children = node.get("children", []) or []
        stack.extend(child for child in children if isinstance(child, dict))
    return matches


@pytest.mark.playwright
@pytest.mark.timeout(120)
@pytest.mark.xdist_group(name="css-view")
def test_doc_prose_code_spans_have_expected_computed_style(
    generated_doc_paths: dict[str, Path],
    css_build_artifact: Path,
) -> None:
    """Inline code tokens should apply the shared DaisyUI capsule styling."""
    doc_path = generated_doc_paths["docs-test-introduction.html"]
    assets_dir = doc_path.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(css_build_artifact, assets_dir / "site.css")

    bun_exe = _require_executable("bun")
    result = subprocess.run(  # noqa: S603 - inputs are controlled fixture paths
        [bun_exe, "x", "css-view", f"file://{doc_path.resolve()}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    payload = msgspec_json.decode(result.stdout)
    tree = typ.cast("dict[str, typ.Any]", payload["payload"]["tree"])
    code_nodes = _extract_nodes_by_tag(tree, "code")
    inline_node = next(
        node for node in code_nodes if node.get("text") == INLINE_CODE_LABEL
    )
    style = inline_node["styleDiff"]

    assert style["background-color"] == "rgb(229, 231, 235)"
    assert "IBM Plex Mono" in style["font-family"]
    assert style["font-size"] == "14px"
    assert style["padding-inline-start"] == style["padding-inline-end"]
    assert style["padding-block-start"] == style["padding-block-end"]


def test_release_version_and_date_prefer_tag_metadata(
    page_config: PageConfig,
    sample_markdown: str,
    markdown_response: dict[str, typ.Any],
) -> None:
    """Release tags should drive the source URL and metadata badges."""

    release_config = dc.replace(
        page_config,
        repo="octo/tool",
        source_url=page_config.source_url,
        doc_path="docs/users-guide.md",
        latest_release="v9.9.9",
        latest_release_published_at=dt.datetime(2024, 12, 25, tzinfo=dt.timezone.utc),
    )
    markdown_response["set_last_modified"]("Mon, 01 Jan 2024 12:00:00 GMT")

    generator = PageContentGenerator(release_config)
    written = generator.run()
    intro_path = next(path for path in written if path.name.endswith("introduction.html"))
    html = intro_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == ["Version 9.9.9", "Updated Dec 25, 2024"]

    requested_url = markdown_response["calls"][0]
    assert "refs/tags/v9.9.9" in requested_url
