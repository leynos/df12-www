"""End-to-end tests for df12 Pages HTML documentation generation.

This module exercises the full documentation pipeline driven by
``df12_pages.generator.PageContentGenerator``. The tests use a
representative markdown fixture together with a minimal ``PageConfig``
to verify that the generated ``docs-*.html`` pages:

* Render the sidebar layout correctly, including grouped navigation
  for top-level sections and their subsections.
* Promote bold headings into table-of-contents style navigation
  entries so important concepts remain discoverable.
* Produce sensible hero titles derived from numbered markdown
  headings (for example, stripping numeric prefixes like ``"1."``).
* Emit consistent metadata badges (version / updated dates) based on
  release tags and/or the latest Git commit, and write the
  ``PAGE_META_TEMPLATE`` JSON file with the expected first-file
  reference.
* Rewrite relative links in the markdown body to canonical GitHub
  ``blob`` URLs pointing at the underlying repository.
* Preserve fenced code blocks and language annotations, ensuring they
  are rendered as ``codehilite`` blocks with the correct
  ``data-language`` attribute.
* Apply the expected DaisyUI/Tailwind capsule styling to inline code
  tokens, which is validated via the external ``css-view`` helper
  taking a computed-style snapshot through ``agent-browser``.

The module relies on several pytest fixtures:

* ``sample_markdown`` defines the markdown used to exercise headings,
  inline code, links, and code blocks.
* ``page_config`` builds a temporary ``PageConfig`` rooted in a
  per-test output directory.
* ``markdown_response`` stubs ``requests.Session`` so content is
  served from in-memory strings while still exposing ``Last-Modified``
  headers.
* ``github_commit_mock`` injects a fake GitHub client, allowing tests
  to control the commit date used in metadata badges without hitting
  the real API.
* ``generated_doc_paths`` and ``generated_docs`` run the generator and
  expose the written HTML pages as ``pathlib.Path`` objects and
  ``BeautifulSoup`` trees respectively.
* ``css_build_artifact`` ensures the Tailwind/DaisyUI CSS bundle
  exists (by invoking ``bun run build``) so the css-view assertions
  reflect the real production styles.

These tests are typically executed as part of the standard test
suite:

* To run everything (including doc generation tests), use::

    make test

* To focus on this module only::

    pytest tests/test_doc_generation.py

The css-view test is marked with ``@pytest.mark.playwright`` (the marker for
browser-backed tests) and requires additional tooling:

* ``bun`` must be available on ``PATH`` to build CSS and run
  ``css-view``.
* ``css-view`` captures through Playwright, so its browser engine must be
  installed, for example via::

    bun x playwright install chromium

Related test data lives entirely within the fixtures in this module;
no external files from ``features/`` or other directories are
required. When extending these tests, prefer augmenting the
``sample_markdown`` fixture and reusing the existing fixtures so new
assertions share the same generation pipeline and remain easy to
reason about.
"""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import functools
import http.server
import json
import logging
import shutil
import socketserver
import subprocess
import sys
import threading
import typing as typ
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from itertools import batched, pairwise
from pathlib import Path
from types import SimpleNamespace

import msgspec.json as msgspec_json
import pytest
import requests
from bs4 import BeautifulSoup
from github3 import exceptions as gh_exc
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from df12_pages import cli
from df12_pages._constants import PAGE_META_TEMPLATE
from df12_pages.cli import _publish_documents, _write_documents, generate
from df12_pages.config import PageConfig, ThemeConfig
from df12_pages.generator import PageContentGenerator
from df12_pages.generator.page_generator import (
    DEFAULT_TEMPLATES_DIR,
    DocumentSource,
    FetchedMarkdown,
    PreparedDocument,
    RenderedDocument,
    WrittenDocument,
    fetch_document,
    fetch_latest_doc_commit,
    publish_document,
    resolve_doc_updated_at,
    resolve_document_source,
)
from df12_pages.generator.renderer import MermaidRenderer

REPO_ROOT = Path(__file__).resolve().parents[1]
#: The build timestamp the rendering tests stamp prepared documents with.
BUILD_TIMESTAMP = dt.datetime(2026, 10, 2, tzinfo=dt.UTC)
INLINE_CODE_LABEL = "introctl"
#: The DOM node type of a text node, as CDP reports it.
TEXT_NODE = 3
#: The computed properties the inline-code assertions read.
CODE_SPAN_PROPS = (
    "background-color,font-family,font-size,padding-inline-start,"
    "padding-inline-end,padding-block-start,padding-block-end"
)

if typ.TYPE_CHECKING:
    from concurrent.futures import Future

    from github3 import GitHub
    from pytest_mock import MockerFixture
else:  # pragma: no cover - typing fallback
    MockerFixture = typ.Any


def _require_executable(name: str) -> str:
    """Resolve an executable on PATH, raising a descriptive error if missing."""
    path = shutil.which(name)
    if not path:
        msg = f"Unable to locate '{name}' on PATH"
        raise FileNotFoundError(msg)
    return path


@contextmanager
def _http_serve(directory: Path) -> typ.Iterator[int]:
    """Serve *directory* over HTTP on a free port, yielding the port number.

    The server runs in a background daemon thread and is shut down on exit.
    Root-relative stylesheet paths (e.g. ``/assets/site.css``) resolve
    correctly when the page is fetched via ``http://127.0.0.1:<port>/``.
    """

    class _SilentHandler(http.server.SimpleHTTPRequestHandler):
        """Serve files without logging each request."""

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Discard the request log line."""
            pass

    handler = functools.partial(_SilentHandler, directory=str(directory))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


@pytest.fixture(scope="module")
def sample_markdown() -> str:
    """Return representative markdown with nested headings for nav tests."""
    return (
        "## 1. Introduction\n"
        "### Overview\n"
        "Intro details.\n\n"
        f"Use the `{INLINE_CODE_LABEL}` tool for bootstrapping.\n\n"
        "**Capabilities**\n"
        "Bullet list of capabilities. For more, see the "
        "[CLI reference](../cli.md#flags).\n\n"
        "### Core Philosophy:\n"
        "Why decisions matter.\n\n"
        "- **Sanitized providers** - The `sanitized_provider` helper returns a "
        "Figment\n"
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


class MarkdownResponseState(typ.TypedDict):
    """State shared by markdown response fixtures."""

    last_modified: str
    calls: list[str]
    set_last_modified: typ.Callable[[str], None]


@pytest.fixture
def markdown_response(
    sample_markdown: str, monkeypatch: pytest.MonkeyPatch
) -> MarkdownResponseState:
    """Provide a fake HTTP response and session state for markdown fetch tests."""
    state: MarkdownResponseState = {
        "last_modified": "Tue, 11 Nov 2025 00:00:00 GMT",
        "calls": [],
        "set_last_modified": lambda value: None,
    }

    class _Response:
        """Stand-in for ``requests.Response`` with a body and headers."""

        def __init__(self, body: str, headers: dict[str, str]) -> None:
            """Store the body text and response headers."""
            self.text = body
            self.headers = headers

        def raise_for_status(self) -> None:  # pragma: no cover - stub
            """Accept every response as successful."""

    def set_last_modified(value: str) -> None:
        """Set the Last-Modified value that later responses report."""
        state["last_modified"] = value

    class _Session:
        """Stand-in for ``requests.Session`` that serves the sample markdown."""

        def mount(
            self, *_args: object, **_kwargs: object
        ) -> None:  # pragma: no cover - stub
            """Ignore adapter mounting; the stub session needs none."""

        def get(self, url: str, timeout: int = 30) -> _Response:
            """Record the URL and return the sample markdown."""
            state["calls"].append(url)
            return _Response(sample_markdown, {"Last-Modified": state["last_modified"]})

        def close(self) -> None:  # pragma: no cover - stub
            """Do nothing; the stub session holds no resources."""

    state["set_last_modified"] = set_last_modified
    monkeypatch.setattr(
        "df12_pages.generator.document_fetch.requests.Session", _Session
    )
    return state


@pytest.fixture(autouse=True)
def github_commit_mock(mocker: MockerFixture) -> dict[str, typ.Any]:
    """Mock GitHub client and repo commits for all tests.

    This autouse fixture stubs ``df12_pages.generator.page_generator.GitHub``
    -- the command boundary that builds the client -- with one that exposes a
    single "latest" commit. It returns a small helper dictionary so individual
    tests can adjust the commit timestamp used in metadata badges, or make the
    lookup fail, without calling the real GitHub API.
    """
    commit_date = dt.datetime(2025, 10, 5, 14, 30, tzinfo=dt.UTC)
    author = SimpleNamespace(date=commit_date)
    committer = SimpleNamespace(date=None)
    commit_payload = SimpleNamespace(author=author, committer=committer)
    latest_commit = SimpleNamespace(commit=commit_payload)

    mock_repo = mocker.Mock()
    mock_repo.commits.return_value = iter([latest_commit])
    mock_client = mocker.Mock()
    mock_client.repository.return_value = mock_repo
    mocker.patch("df12_pages.generator.page_generator.GitHub", return_value=mock_client)

    def set_date(value: dt.datetime) -> None:
        """Set the author date reported by the mocked latest commit."""
        author.date = value

    def fail_commits() -> None:
        """Make the commit lookup fail, as an unreadable repository would."""
        mock_repo.commits.side_effect = gh_exc.GitHubException("unavailable")

    def fail_repository() -> None:
        """Make the repository lookup fail, as an unknown repository would."""
        mock_client.repository.side_effect = gh_exc.GitHubException("unavailable")

    return {
        "set_date": set_date,
        "fail_commits": fail_commits,
        "fail_repository": fail_repository,
    }


@pytest.fixture
def generated_doc_paths(
    page_config: PageConfig,
    markdown_response: MarkdownResponseState,
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
def css_build_artifact(built_site: Path) -> Path:
    """Ensure the Tailwind/Daisy build artifact exists for tests."""
    css_path = built_site.parent / "assets" / "site.css"
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
    headings = [h.get_text(strip=True) for g in groups if (h := g.select_one("h3"))]
    assert headings == [
        "Introduction",
        "Getting Started",
    ], (
        "expected sidebar groups to be ['Introduction', 'Getting Started'], "
        f"got {headings!r}"
    )

    intro_links = [a.get_text(strip=True) for a in groups[0].select("a")]
    assert intro_links[0] == "Introduction", (
        f"expected first intro link to be 'Introduction', got {intro_links[0]!r}"
    )
    assert "Overview" in intro_links[1], (
        "expected 'Overview' to be present in second intro link, "
        f"got {intro_links[1]!r}"
    )
    assert "Capabilities" in intro_links[2], (
        "expected 'Capabilities' to be present in third intro link, "
        f"got {intro_links[2]!r}"
    )
    assert "Core Philosophy" in intro_links[3], (
        "expected 'Core Philosophy' to be present in fourth intro link, "
        f"got {intro_links[3]!r}"
    )


def test_only_one_sidebar_link_flagged_active(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Exactly one nav link should be marked as active for a page."""
    soup = generated_docs["docs-test-getting-started.html"]
    active_titles = soup.select(".doc-nav-group__title.is-active")
    assert len(active_titles) == 1, (
        "Expected exactly one active nav title in 'docs-test-getting-started.html', "
        f"found {len(active_titles)}"
    )


def test_bold_heading_promoted_to_nav_entry(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Standalone bold headings must surface within the contents nav."""
    soup = generated_docs["docs-test-introduction.html"]
    nav_labels = [
        span.get_text(strip=True) for span in soup.select(".doc-nav__list a span")
    ]
    assert "Capabilities" in nav_labels, (
        "expected 'Capabilities' to be present in nav labels"
    )
    assert "Core Philosophy" in nav_labels, (
        "expected 'Core Philosophy' to be present in nav labels"
    )


def test_hero_title_strips_numbering(generated_docs: dict[str, BeautifulSoup]) -> None:
    """Hero titles should omit numbering prefixes from H2 markdown."""
    soup = generated_docs["docs-test-introduction.html"]
    title_tag = soup.select_one(".doc-hero__title")
    assert title_tag is not None, "Expected hero title element to exist"
    hero_title = title_tag.get_text(strip=True)
    assert hero_title, "Expected hero title text to be non-empty"
    assert hero_title == "Introduction", (
        f"Expected hero title to equal 'Introduction' but got {hero_title!r}"
    )


def test_doc_meta_uses_commit_date(
    page_config: PageConfig,
    markdown_response: MarkdownResponseState,
    github_commit_mock: dict[str, typ.Any],
) -> None:
    """When releases are absent, rely on the last commit timestamp."""
    commit_dt = dt.datetime(2025, 10, 9, 9, 0, tzinfo=dt.UTC)
    github_commit_mock["set_date"](commit_dt)

    generator = PageContentGenerator(page_config)
    written = generator.run()
    intro_path = next(
        path for path in written if path.name.endswith("introduction.html")
    )
    soup = BeautifulSoup(intro_path.read_text(encoding="utf-8"), "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == ["Updated Oct 09, 2025"], (
        f"unexpected meta_items: {meta_items!r} (expected ['Updated Oct 09, 2025'])"
    )


def test_doc_meta_uses_the_source_date_when_no_release_or_commit_exists(
    page_config: PageConfig,
    markdown_response: MarkdownResponseState,
    github_commit_mock: dict[str, typ.Any],
) -> None:
    """Without a release or readable commits, the response date decorates the page."""
    github_commit_mock["fail_commits"]()
    markdown_response["set_last_modified"]("Sat, 04 Jan 2025 18:30:00 GMT")

    generator = PageContentGenerator(page_config)
    written = generator.run()
    intro_path = next(
        path for path in written if path.name.endswith("introduction.html")
    )
    soup = BeautifulSoup(intro_path.read_text(encoding="utf-8"), "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == ["Updated Jan 04, 2025"], (
        "the page must show when the document it displays last changed, "
        f"got {meta_items!r}"
    )


def test_a_failed_commit_lookup_is_logged_and_the_page_still_renders(
    page_config: PageConfig,
    markdown_response: MarkdownResponseState,
    github_commit_mock: dict[str, typ.Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A GitHub error is reported against the page and never stops the render."""
    github_commit_mock["fail_repository"]()
    markdown_response["set_last_modified"]("Sat, 04 Jan 2025 18:30:00 GMT")

    with caplog.at_level(logging.WARNING, logger="df12_pages.generator.page_generator"):
        written = PageContentGenerator(page_config).run()

    messages = [record.getMessage() for record in caplog.records]
    assert any(page_config.key in message for message in messages), (
        f"the failure must name page {page_config.key!r}: {messages!r}"
    )

    intro_path = next(
        path for path in written if path.name.endswith("introduction.html")
    )
    soup = BeautifulSoup(intro_path.read_text(encoding="utf-8"), "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == ["Updated Jan 04, 2025"], (
        f"a failed lookup must fall through to the response date, got {meta_items!r}"
    )


def test_resolve_doc_updated_at_reads_a_naive_commit_date_as_utc(
    page_config: PageConfig,
) -> None:
    """A commit date without a timezone is UTC, which is what GitHub means."""
    naive = dt.datetime(2025, 10, 9, 9, 0)  # noqa: DTZ001 -- naive is the input under test
    latest = SimpleNamespace(
        commit=SimpleNamespace(
            author=SimpleNamespace(date=naive),
            committer=SimpleNamespace(date=None),
        )
    )

    resolved = resolve_doc_updated_at(page_config, commit=latest)

    assert resolved == naive.replace(tzinfo=dt.UTC), (
        f"a naive commit date must be read as UTC, got {resolved!r}"
    )


def test_resolve_doc_updated_at_prefers_the_release_without_a_commit(
    page_config: PageConfig,
) -> None:
    """The query reads only its arguments, so a release date needs no commit."""
    release = dt.datetime(2025, 1, 2, tzinfo=dt.UTC)
    page = dc.replace(page_config, latest_release_published_at=release)

    assert resolve_doc_updated_at(page, commit=None) == release, (
        "the configured release date must answer without a commit payload"
    )


def test_fetch_latest_doc_commit_rejects_a_malformed_slug_without_a_lookup(
    page_config: PageConfig, mocker: MockerFixture
) -> None:
    """A slug that names no repository is a page with no date, not a lookup."""
    page = dc.replace(page_config, repo="not-a-slug")
    client = mocker.Mock()

    resolved = fetch_latest_doc_commit(page, client=typ.cast("GitHub", client))

    assert resolved is None, "a malformed slug must yield no commit"
    client.repository.assert_not_called()


def test_indented_fenced_block_renders_codehilite(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Indented fenced code blocks should render as highlighted HTML."""
    soup = generated_docs["docs-test-introduction.html"]
    code_blocks = soup.select(".doc-article .codehilite code")
    assert any("use figment" in block.get_text() for block in code_blocks), (
        "expected at least one code block to contain 'use figment'"
    )
    assert any(
        (parent := block.find_parent("div", class_="codehilite")) is not None
        and parent.get("data-language") == "rust"
        for block in code_blocks
    ), "expected at least one code block parent div to have data-language='rust'"


def test_default_layout_content_not_duplicated(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Sections without headings should render body content exactly once."""
    soup = generated_docs["docs-test-introduction.html"]
    article = soup.select_one(".doc-article")
    assert article is not None, "expected .doc-article element in generated doc"
    html = article.decode_contents()
    assert html.count("Sanitized providers") == 1, (
        "expected 'Sanitized providers' to appear exactly once in generated doc HTML"
    )


def test_relative_links_rewritten_to_github(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Relative links should point to the original GitHub repository blob URL."""
    soup = generated_docs["docs-test-introduction.html"]
    link = soup.select_one("a[href*='github.com']")
    assert link is not None, "expected GitHub link in generated docs"
    href = link.get("href")
    assert href is not None, "expected GitHub link to have href attribute"
    assert href == "https://github.com/df12/testdocs/blob/main/cli.md#flags", (
        f"expected href to match original GitHub blob URL, got {href!r}"
    )


def test_first_section_metadata_written(
    page_config: PageConfig,
    generated_doc_paths: dict[str, Path],
) -> None:
    """Ensure first section metadata is written alongside generated docs."""
    meta_path = page_config.output_dir / PAGE_META_TEMPLATE.format(key=page_config.key)
    assert meta_path.exists(), f"expected meta file to exist at {meta_path!s}"
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata.get("first_file") == "docs-test-introduction.html", (
        "expected metadata['first_file'] to be 'docs-test-introduction.html', "
        f"got {metadata.get('first_file')!r} in {metadata!r}"
    )


def test_sidebar_shows_label_and_description(
    generated_docs: dict[str, BeautifulSoup],
) -> None:
    """Sidebar should highlight the tool label and description."""
    soup = generated_docs["docs-test-introduction.html"]
    eyebrow = soup.select_one(".doc-sidebar__eyebrow")
    assert eyebrow is not None, "expected .doc-sidebar__eyebrow element to be present"
    assert eyebrow.get_text(strip=True) == "Test Docs", (
        f"expected eyebrow text 'Test Docs', got {eyebrow.get_text(strip=True)!r}"
    )
    body = soup.select_one(".doc-sidebar__body")
    assert body is not None, "expected .doc-sidebar__body element to be present"
    assert body.get_text(strip=True) == "Fixture Description", (
        f"expected body text 'Fixture Description', got {body.get_text(strip=True)!r}"
    )


class _CdpNode(typ.TypedDict):
    """The fields of a css-view CDP snapshot node that these tests read."""

    index: int
    nodeType: int
    tagName: typ.NotRequired[str]
    textContent: typ.NotRequired[str | None]
    parentIndex: typ.NotRequired[int | None]
    computedStyles: typ.NotRequired[dict[str, str]]


def _cdp_element_with_text(nodes: list[_CdpNode], tag: str, text: str) -> _CdpNode:
    """Return the *tag* element in a CDP snapshot whose text node reads *text*.

    CDP snapshots are a flat node list: an element's text sits on a child
    text node that points back to it through ``parentIndex``.
    """
    by_index = {node["index"]: node for node in nodes}
    for node in nodes:
        if (
            node.get("nodeType") != TEXT_NODE
            or (node.get("textContent") or "").strip() != text
        ):
            continue
        parent = by_index.get(node.get("parentIndex"))
        if parent is not None and str(parent.get("tagName", "")).lower() == tag:
            return parent
    msg = f"no <{tag}> reading {text!r} in the snapshot"
    raise AssertionError(msg)


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
    with _http_serve(doc_path.parent) as port:
        url = f"http://127.0.0.1:{port}/{doc_path.name}"
        try:
            result = subprocess.run(  # noqa: S603 - FIXME: inputs are controlled fixture paths in tests; no user-provided arguments
                [
                    bun_exe,
                    "x",
                    "css-view",
                    # The assertions below read the flat CDP node list.
                    "--mode",
                    "cdp",
                    "--props",
                    CODE_SPAN_PROPS,
                    url,
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                timeout=90,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - environment guard
            pytest.skip(f"css-view timed out: {exc}")
    payload = msgspec_json.decode(result.stdout)
    nodes = typ.cast("list[_CdpNode]", payload["payload"]["nodes"])
    inline_node = _cdp_element_with_text(nodes, "code", INLINE_CODE_LABEL)
    style = inline_node["computedStyles"]

    assert style["background-color"] == "rgb(229, 231, 235)"
    assert "IBM Plex Mono" in style["font-family"]
    assert style["font-size"] == "14px"
    assert style["padding-inline-start"] == style["padding-inline-end"]
    assert style["padding-block-start"] == style["padding-block-end"]


def test_release_version_and_date_prefer_tag_metadata(
    page_config: PageConfig,
    sample_markdown: str,
    markdown_response: MarkdownResponseState,
) -> None:
    """Release tags should drive the source URL and metadata badges."""
    release_config = dc.replace(
        page_config,
        repo="octo/tool",
        source_url=page_config.source_url,
        doc_path="docs/users-guide.md",
        latest_release="v9.9.9",
        latest_release_published_at=dt.datetime(2024, 12, 25, tzinfo=dt.UTC),
    )
    markdown_response["set_last_modified"]("Mon, 01 Jan 2024 12:00:00 GMT")

    generator = PageContentGenerator(release_config)
    written = generator.run()
    intro_path = next(
        path for path in written if path.name.endswith("introduction.html")
    )
    html = intro_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == [
        "Version 9.9.9",
        "Updated Dec 25, 2024",
    ], (
        "expected meta items to be ['Version 9.9.9', 'Updated Dec 25, 2024'], "
        f"got {meta_items!r}"
    )

    requested_url = markdown_response["calls"][0]
    assert "refs/tags/v9.9.9" in requested_url, (
        f"expected request URL {requested_url!r} to reference release tag 'v9.9.9'"
    )


def test_release_fetch_falls_back_to_branch_when_tag_missing_doc(
    page_config: PageConfig,
    sample_markdown: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 404 on the release-pinned guide URL falls back to the branch source."""
    release_config = dc.replace(
        page_config,
        repo="octo/tool",
        source_url=page_config.source_url,
        doc_path="docs/users-guide.md",
        latest_release="v9.9.9",
        latest_release_published_at=dt.datetime(2024, 12, 25, tzinfo=dt.UTC),
    )
    calls: list[str] = []

    class _Response:
        """Stand-in for ``requests.Response`` with a status code and body."""

        def __init__(self, status_code: int, body: str) -> None:
            """Store the status code, body text, and Last-Modified header."""
            self.status_code = status_code
            self.text = body
            self.headers = {"Last-Modified": "Mon, 01 Jan 2024 12:00:00 GMT"}

        def raise_for_status(self) -> None:
            """Raise HTTPError, carrying this response, for 4xx and 5xx."""
            if self.status_code >= http.HTTPStatus.BAD_REQUEST:
                msg = f"{self.status_code} for test"
                raise requests.HTTPError(msg, response=self)

    class _Session:
        """Stand-in for ``requests.Session`` that returns 404 for tag URLs."""

        def mount(self, *_args: object, **_kwargs: object) -> None:
            """Ignore adapter mounting; the stub session needs none."""

        def get(self, url: str, timeout: int = 30) -> _Response:
            """Record the URL, then return 404 for tags or the sample markdown."""
            calls.append(url)
            if "refs/tags/" in url:
                return _Response(404, "missing")
            return _Response(200, sample_markdown)

        def close(self) -> None:
            """Do nothing; the stub session holds no resources."""

    monkeypatch.setattr(
        "df12_pages.generator.document_fetch.requests.Session", _Session
    )

    generator = PageContentGenerator(release_config)
    with caplog.at_level(logging.INFO, logger="df12_pages.generator.document_fetch"):
        written = generator.run()

    fallback_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "df12_pages.generator.document_fetch"
    ]
    assert any("v9.9.9" in message for message in fallback_logs), (
        f"the release-to-branch fallback must be logged, got {fallback_logs!r}"
    )
    assert all(url not in message for message in fallback_logs for url in calls), (
        f"the fallback log must not name either URL, got {fallback_logs!r}"
    )

    expected_fetches = 2
    assert len(calls) == expected_fetches, (
        f"expected tag fetch then branch fallback, got {calls!r}"
    )
    assert "refs/tags/v9.9.9" in calls[0]
    assert calls[1] == release_config.source_url
    assert generator.source.version == "v9.9.9", (
        "the configured source still records the release pin; the fetched "
        "provenance is what drops it"
    )

    intro_path = next(
        path for path in written if path.name.endswith("introduction.html")
    )
    soup = BeautifulSoup(intro_path.read_text(encoding="utf-8"), "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert "Version 9.9.9" not in meta_items, (
        f"fallback content must not claim the release version, got {meta_items!r}"
    )

    hrefs = [anchor.get("href", "") for anchor in soup.select("a[href*='cli.md']")]
    assert hrefs == ["https://github.com/octo/tool/blob/main/cli.md#flags"], (
        "a link inside branch content must point into the branch that answered, "
        f"got {hrefs!r}"
    )


def test_a_retained_release_document_keeps_its_links_after_a_fallback(
    page_config: PageConfig,
    tmp_path: Path,
) -> None:
    """A prepared release document renders with its own ref after a fallback.

    Preparation captures the ref that answered each fetch. Rendering the
    branch-fallback document first must not retarget the retained release
    document, whose links point at the release it was fetched from.
    """
    page = dc.replace(page_config, output_dir=tmp_path / "out")
    generator = PageContentGenerator(page, fetcher=_forbid_fetch)
    body = "## Intro\n\nSee [flags](./cli.md#flags).\n"
    release = generator.prepare_document(body, link_ref="v1.0.0")
    fallback = generator.prepare_document(body, link_ref="main")

    def render_links(prepared: PreparedDocument) -> list[str]:
        """Render ``prepared`` and return its rewritten link targets."""
        document = generator.render_document(
            prepared,
            source_url=page.source_url,
            version_display=None,
            page_description="Fixture description",
            generated_at=BUILD_TIMESTAMP,
        )
        soup = BeautifulSoup(document.sections[0][1], "html.parser")
        return [
            href
            for anchor in soup.select("a[href*='cli.md']")
            if isinstance(href := anchor.get("href"), str)
        ]

    assert render_links(fallback) == [
        "https://github.com/df12/testdocs/blob/main/docs/cli.md#flags"
    ]
    assert render_links(release) == [
        "https://github.com/df12/testdocs/blob/v1.0.0/docs/cli.md#flags"
    ], "a retained document must keep the ref its own fetch answered from"


def _http_error(status_code: int) -> requests.HTTPError:
    """Return an ``HTTPError`` carrying a response with *status_code*."""
    response = SimpleNamespace(status_code=status_code)
    return requests.HTTPError(f"{status_code} for test", response=response)


class _ScriptedSession:
    """A session that answers each URL from a script of outcomes.

    An outcome is a body string, an ``HTTPError`` to raise, or a
    ``(body, headers)`` pair when the response's headers matter.
    """

    def __init__(
        self,
        outcomes: dict[str, str | requests.HTTPError | tuple[str, dict[str, str]]],
    ) -> None:
        """Store the scripted outcome for each URL."""
        self._outcomes = outcomes
        self.requested: list[str] = []

    def get(self, url: str, timeout: int = 30) -> SimpleNamespace:
        """Record the URL, then return its body and headers or raise its error."""
        self.requested.append(url)
        outcome = self._outcomes[url]
        if isinstance(outcome, requests.HTTPError):
            raise outcome
        text, headers = outcome if isinstance(outcome, tuple) else (outcome, {})
        return SimpleNamespace(
            text=text, headers=headers, raise_for_status=lambda: None
        )


def test_fetch_document_drops_the_pin_when_the_release_lacks_the_document() -> None:
    """A 404 on the release URL falls back to the branch and drops the pin."""
    branch_url = "https://example.test/main/docs/guide.md"
    release_url = "https://example.test/refs/tags/v1.2.3/docs/guide.md"
    source = DocumentSource(
        source_url=branch_url,
        release_url=release_url,
        version="v1.2.3",
        branch="main",
    )
    released = dt.datetime(2024, 12, 25, tzinfo=dt.UTC)
    branch_changed = dt.datetime(2024, 12, 30, 9, 0, tzinfo=dt.UTC)
    session = _ScriptedSession(
        {
            release_url: _http_error(404),
            branch_url: (
                "# Branch text",
                {"Last-Modified": "Mon, 30 Dec 2024 09:00:00 GMT"},
            ),
        }
    )

    fetched = fetch_document(
        source, updated_at=released, session=typ.cast("requests.Session", session)
    )

    assert session.requested == [release_url, branch_url], (
        "the release URL must be tried before the branch"
    )
    assert fetched == FetchedMarkdown(
        text="# Branch text",
        source_url=branch_url,
        version=None,
        updated_at=branch_changed,
        ref="main",
    ), "the branch copy keeps its own Last-Modified but not the release date"


def test_fetch_document_keeps_the_pin_when_the_release_answers() -> None:
    """The release-pinned document keeps its URL, version pin, and date."""
    branch_url = "https://example.test/main/docs/guide.md"
    release_url = "https://example.test/refs/tags/v1.2.3/docs/guide.md"
    source = DocumentSource(
        source_url=branch_url,
        release_url=release_url,
        version="v1.2.3",
        branch="main",
    )
    released = dt.datetime(2024, 12, 25, tzinfo=dt.UTC)
    session = _ScriptedSession(
        {
            release_url: (
                "# Released text",
                {"Last-Modified": "Mon, 30 Dec 2024 09:00:00 GMT"},
            )
        }
    )

    fetched = fetch_document(
        source, updated_at=released, session=typ.cast("requests.Session", session)
    )

    assert session.requested == [release_url], "the branch must not be consulted"
    assert fetched == FetchedMarkdown(
        text="# Released text",
        source_url=release_url,
        version="v1.2.3",
        updated_at=released,
        ref="v1.2.3",
    ), "the known release date outranks the response's Last-Modified"


def test_fetch_document_falls_back_to_a_response_date_without_a_known_one() -> None:
    """With no release or commit date, the response's Last-Modified is used."""
    url = "https://example.test/main/docs/guide.md"
    session = _ScriptedSession(
        {url: ("# Text", {"Last-Modified": "Sat, 04 Jan 2025 18:30:00 GMT"})}
    )

    fetched = fetch_document(
        DocumentSource(url), session=typ.cast("requests.Session", session)
    )

    assert fetched.updated_at == dt.datetime(2025, 1, 4, 18, 30, tzinfo=dt.UTC), (
        "the response Last-Modified date stands in for a missing known date"
    )


def test_fetch_document_uses_a_known_date_for_a_branch_only_source() -> None:
    """The branch is the first candidate, so a supplied date outranks the header."""
    url = "https://example.test/main/docs/guide.md"
    known = dt.datetime(2024, 12, 25, tzinfo=dt.UTC)
    session = _ScriptedSession(
        {url: ("# Text", {"Last-Modified": "Mon, 30 Dec 2024 09:00:00 GMT"})}
    )

    fetched = fetch_document(
        DocumentSource(url, branch="main"),
        updated_at=known,
        session=typ.cast("requests.Session", session),
    )

    assert fetched.updated_at == known, (
        "the caller's date applies whenever the first candidate answers"
    )
    assert fetched.version is None, "a branch source carries no release pin"
    assert fetched.ref == "main", "branch links must point into the branch"


def test_an_explicit_source_override_keeps_the_known_date_and_names_no_ref(
    page_config: PageConfig,
) -> None:
    """An override is a first candidate with no branch or release of its own."""
    url = "https://example.test/override/guide.md"
    known = dt.datetime(2024, 12, 25, tzinfo=dt.UTC)
    source = resolve_document_source(page_config, override=url)
    session = _ScriptedSession(
        {url: ("# Override", {"Last-Modified": "Mon, 30 Dec 2024 09:00:00 GMT"})}
    )

    assert source.branch is None, "an override names no branch to rewrite links into"
    fetched = fetch_document(
        source, updated_at=known, session=typ.cast("requests.Session", session)
    )

    assert fetched.updated_at == known, (
        "the caller's date applies whenever the first candidate answers"
    )
    assert fetched.version is None, "an override carries no release pin"
    assert fetched.ref is None, "an override names no tree for relative links"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Last-Modified": ""},
        {"Last-Modified": "not a date"},
    ],
    ids=["absent", "empty", "malformed"],
)
def test_fetch_document_ignores_a_missing_or_unparseable_source_date(
    headers: dict[str, str],
) -> None:
    """A header that is absent, empty or malformed leaves the date unset."""
    url = "https://example.test/main/docs/guide.md"
    session = _ScriptedSession({url: ("# Text", headers)})

    fetched = fetch_document(
        DocumentSource(url), session=typ.cast("requests.Session", session)
    )

    assert fetched.updated_at is None, (
        "an absent, empty or malformed header must leave the date unset"
    )
    assert fetched.text == "# Text", "the body is served regardless of the header"


def test_fetch_document_does_not_fall_back_on_an_unrelated_failure() -> None:
    """Only a missing release document earns the branch fallback."""
    branch_url = "https://example.test/main/docs/guide.md"
    release_url = "https://example.test/refs/tags/v1.2.3/docs/guide.md"
    source = DocumentSource(
        source_url=branch_url, release_url=release_url, version="v1.2.3"
    )
    session = _ScriptedSession({release_url: _http_error(500), branch_url: "text"})

    with pytest.raises(requests.HTTPError):
        fetch_document(source, session=typ.cast("requests.Session", session))

    assert session.requested == [release_url], (
        "a server error must surface, not be masked by the branch copy"
    )


class _RecordingExecutor(ThreadPoolExecutor):
    """A worker pool that remembers the futures it submits, in submit order."""

    def __init__(self, max_workers: int) -> None:
        """Start the pool with an empty record of what it has been given."""
        super().__init__(max_workers=max_workers)
        self._submitted: list[Future[RenderedDocument]] = []
        self._submitted_changed = threading.Condition()

    def submit(
        self,
        fn: typ.Callable[..., RenderedDocument],
        /,
        *args: object,
        **kwargs: object,
    ) -> Future[RenderedDocument]:
        """Record the future so a stub can wait for another bundle to finish."""
        future = super().submit(fn, *args, **kwargs)
        with self._submitted_changed:
            self._submitted.append(future)
            self._submitted_changed.notify_all()
        return future

    def future_at(
        self, index: int, timeout: float = 5
    ) -> Future[RenderedDocument] | None:
        """Wait for the future submitted at ``index`` and return it.

        Returns ``None`` when nothing is submitted at that index within
        ``timeout``, so a stub can fail an assertion rather than hang.
        """
        with self._submitted_changed:
            self._submitted_changed.wait_for(
                lambda: len(self._submitted) > index, timeout
            )
            if index >= len(self._submitted):
                return None
            return self._submitted[index]


def _stub_render_in_order(  # noqa: PLR0913 -- one knob per ordering scenario
    monkeypatch: pytest.MonkeyPatch,
    *,
    reverse_completion: bool = False,
    keys: list[str] | None = None,
    completion_orders: list[list[int]] | None = None,
    batch_size: int | None = None,
    distinct_paths: bool = False,
) -> None:
    """Replace rendering with a stub that writes one identifiable section.

    Parameters
    ----------
    monkeypatch
        Fixture used to replace :meth:`PageContentGenerator.render` and the
        pool class it runs in.
    reverse_completion
        Make the later bundle's future complete before the earlier bundle
        returns, so a writer that published in completion order would invert
        them.
    keys
        The page keys in configuration order, indexed by ``completion_orders``.
    completion_orders
        One permutation per batch, giving the batch-local indices in the order
        the stub must let them finish. Each bundle waits on the next one's
        future, so the drawn permutation is forced rather than left to the
        scheduler. A batch's chain never leaves that batch, so several batches
        can each have their own.
    batch_size
        Bundles submitted in one batch; required with ``completion_orders`` so
        each batch's futures can be mapped back to their global submission
        position.
    distinct_paths
        Give each bundle a file only it writes, ahead of the shared one. The
        returned paths then name their bundle, so publication order can be
        read from the path sequence instead of only from the shared file's
        final owner.
    """
    pools: list[_RecordingExecutor] = []

    def make_executor(*, max_workers: int) -> _RecordingExecutor:
        """Record the pool so the stub can reach the futures it submits."""
        pool = _RecordingExecutor(max_workers)
        pools.append(pool)
        return pool

    successors: dict[str, int] = {}
    if completion_orders and keys:
        if batch_size is None:
            msg = "completion_orders needs batch_size so batch futures are known"
            raise ValueError(msg)
        for batch_index, order in enumerate(completion_orders):
            start = batch_index * batch_size
            batch = keys[start : start + batch_size]
            for current, following in pairwise(order):
                successors[batch[current]] = start + following

    def wait_for_future(pool: _RecordingExecutor, index: int, key: str) -> None:
        """Block until the future at ``index`` has returned a document."""
        future = pool.future_at(index)
        assert future is not None, (
            f"bundle {key!r} waited on a future that was never submitted"
        )
        # A future completing is a fact about that bundle's return, not a race
        # the scheduler can reorder, so the drawn order really happens.
        assert future.result(timeout=5), (
            f"bundle {key!r} waited on a future that returned nothing"
        )

    def render(generator: PageContentGenerator) -> RenderedDocument:
        """Return a document whose content names the bundle that produced it."""
        key = generator.page.key
        if reverse_completion and key == "first":
            assert pools, "the concurrent writer created no pool to wait on"
            wait_for_future(pools[0], 1, key)
        if key in successors:
            assert pools, "the concurrent writer created no pool to wait on"
            wait_for_future(pools[0], successors[key], key)
        prefix = generator.page.filename_prefix
        sections = []
        if distinct_paths:
            sections.append((f"{prefix}{key}.html", f"Content from {key}."))
        sections.append((f"{prefix}shared-heading.html", f"Content from {key}."))
        return RenderedDocument(
            generator.page.output_dir,
            generator.page.output_dir / PAGE_META_TEMPLATE.format(key=key),
            sections,
        )

    monkeypatch.setattr(cli, "ThreadPoolExecutor", make_executor)
    monkeypatch.setattr(PageContentGenerator, "render", render)


def test_write_documents_serial_builds_publish_in_configuration_order(
    page_config: PageConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With one worker, bundles publish in the order they are configured."""
    _stub_render_in_order(monkeypatch)
    keys = [f"page{index}" for index in range(3)]
    pages = [
        dc.replace(page_config, key=key, output_dir=tmp_path / key) for key in keys
    ]

    paths = list(_write_documents(pages, 1))

    assert [path.parent.name for path in paths] == keys
    assert [path.read_text() for path in paths] == [
        f"Content from {key}." for key in keys
    ]


def test_write_documents_spanning_batches_publish_in_configuration_order(
    page_config: PageConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More pages than workers still publish in configuration order per batch."""
    _stub_render_in_order(monkeypatch)
    keys = [f"page{index}" for index in range(5)]
    pages = [
        dc.replace(page_config, key=key, output_dir=tmp_path / key) for key in keys
    ]

    paths = list(_write_documents(pages, 2))

    assert [path.parent.name for path in paths] == keys


def test_write_documents_reports_the_effective_worker_count(
    page_config: PageConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The concurrent path reports the worker count and per-bundle timing."""
    _stub_render_in_order(monkeypatch)
    pages = [
        dc.replace(
            page_config, key=f"page{index}", output_dir=tmp_path / f"page{index}"
        )
        for index in range(2)
    ]

    with caplog.at_level(logging.INFO, logger="df12_pages.cli"):
        list(_write_documents(pages, 2))

    assert "rendering 2 document bundle(s) with 2 effective worker(s)" in caplog.text
    assert "(limit 2)" in caplog.text
    assert "rendered document bundle 'page0'" in caplog.text
    assert "wrote 2 document bundle(s)" in caplog.text


@pytest.mark.parametrize(
    ("page_count", "workers", "effective"),
    [
        pytest.param(0, 8, 0, id="empty"),
        pytest.param(1, 8, 1, id="single-page"),
        pytest.param(3, 1, 1, id="serial"),
        pytest.param(3, 8, 3, id="bundle-limited"),
    ],
)
def test_write_documents_reports_the_effective_concurrency(  # noqa: PLR0913, PLR0917
    page_config: PageConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    page_count: int,
    workers: int,
    effective: int,
) -> None:
    """The configured limit is reported beside what can actually run."""
    _stub_render_in_order(monkeypatch)
    pages = [
        dc.replace(
            page_config, key=f"page{index}", output_dir=tmp_path / f"page{index}"
        )
        for index in range(page_count)
    ]

    with caplog.at_level(logging.INFO, logger="df12_pages.cli"):
        list(_write_documents(pages, workers))

    assert (
        f"rendering {page_count} document bundle(s) with {effective} effective"
        f" worker(s) (limit {workers})" in caplog.text
    )


#: The documented default concurrency for documentation bundles.
EXPECTED_DEFAULT_WORKERS = 8


def test_the_doc_worker_default_is_eight(
    page_config: PageConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI default reaches the writer unchanged."""
    assert cli.DEFAULT_DOC_WORKERS == EXPECTED_DEFAULT_WORKERS
    page = dc.replace(page_config, key="main-page", output_dir=tmp_path)
    site_config = SimpleNamespace(
        pages={"main-page": page},
        sites={},
        docs_index_output=None,
        get_page=lambda key: {"main-page": page}[key],
    )
    recorded = _record_generated_workers(monkeypatch, site_config)

    generate(page="main-page")

    assert recorded == [cli.DEFAULT_DOC_WORKERS]


@given(
    page_count=st.integers(min_value=1, max_value=6),
    workers=st.integers(min_value=1, max_value=4),
)
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_any_worker_count_publishes_in_configuration_order(
    page_count: int,
    workers: int,
    page_config: PageConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overlapping paths follow configuration order whatever the pool size."""
    _stub_render_in_order(monkeypatch)
    keys = [f"page{index}" for index in range(page_count)]
    pages = [dc.replace(page_config, key=key, output_dir=tmp_path) for key in keys]

    paths = list(_write_documents(pages, workers))

    assert [path.name for path in paths] == ["docs-test-shared-heading.html"] * (
        page_count
    )
    assert paths[-1].read_text() == f"Content from {keys[-1]}."
    for page in pages:
        metadata = tmp_path / PAGE_META_TEMPLATE.format(key=page.key)
        assert json.loads(metadata.read_text()) == {"first_file": paths[0].name}


@given(data=st.data())
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_any_completion_permutation_publishes_in_configuration_order(
    data: st.DataObject,
    page_config: PageConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publication order follows configuration, whatever order renders finish.

    Both the worker count and the bundle count are drawn, so the run spans one
    or more worker-sized batches, and each batch is given its own drawn
    completion permutation. Every permutation is forced by making each bundle
    wait on the next one's future, so this asserts against a known completion
    order rather than against whatever the scheduler happened to produce.
    """
    workers = data.draw(st.integers(min_value=2, max_value=3), label="workers")
    minimum_pages = workers + 1
    page_count = data.draw(
        st.integers(min_value=minimum_pages, max_value=workers * 3),
        label="page_count",
    )
    keys = [f"page{index}" for index in range(page_count)]
    batches = [
        list(batch) for batch in batched(range(page_count), workers, strict=False)
    ]
    completion_orders = [
        list(data.draw(st.permutations(range(len(batch))), label=f"order{batch[0]}"))
        for batch in batches
    ]
    _stub_render_in_order(
        monkeypatch,
        keys=keys,
        completion_orders=completion_orders,
        batch_size=workers,
        distinct_paths=True,
    )
    pages = [dc.replace(page_config, key=key, output_dir=tmp_path) for key in keys]

    paths = list(_write_documents(pages, workers))

    prefix = page_config.filename_prefix
    shared_name = f"{prefix}shared-heading.html"
    expected = [
        tmp_path / filename
        for key in keys
        for filename in (f"{prefix}{key}.html", shared_name)
    ]
    assert paths == expected, (
        "publication must follow configuration order, not completion order"
    )
    for key in keys:
        own = tmp_path / f"{prefix}{key}.html"
        assert own.read_text() == f"Content from {key}.", (
            "each bundle's own file must hold that bundle's document"
        )
    assert paths[-1].read_text() == f"Content from {keys[-1]}.", (
        "the last-configured bundle must win the shared path"
    )
    for page in pages:
        metadata = tmp_path / PAGE_META_TEMPLATE.format(key=page.key)
        assert json.loads(metadata.read_text()) == {
            "first_file": f"{prefix}{page.key}.html"
        }


#: The calls the no-I/O tests forbid: the clock, the environment and the CLI.
FORBIDDEN_IN_RENDER = (
    "df12_pages.generator.page_generator.build_timestamp",
    "df12_pages.generator.renderer.subprocess.run",
    "os.getenv",
)


@contextmanager
def _watched(monkeypatch: pytest.MonkeyPatch) -> typ.Iterator[list[str]]:
    """Record file reads and reject the build clock, environment and Mermaid CLI.

    Yields the list of files read, so a test can assert on it once the watched
    work has returned.
    """
    reads: list[str] = []
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes

    def _record_read(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        """Record a text read and still perform it."""
        reads.append(str(self))
        return original_read_text(self, encoding=encoding, errors=errors)

    def _record_read_bytes(self: Path) -> bytes:
        """Record a byte read and still perform it."""
        reads.append(str(self))
        return original_read_bytes(self)

    def _forbidden(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Reject an unexpected clock, environment or subprocess lookup."""
        msg = (
            "the watched work must read no clock or environment and start no subprocess"
        )
        raise AssertionError(msg)

    def _no_metadata(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Reject a path resolution or metadata lookup."""
        msg = "the watched work must resolve no path and stat no file"
        raise AssertionError(msg)

    monkeypatch.setattr(Path, "read_text", _record_read)
    monkeypatch.setattr(Path, "read_bytes", _record_read_bytes)
    for name in ("resolve", "stat", "lstat"):
        monkeypatch.setattr(Path, name, _no_metadata)
    for dotted in FORBIDDEN_IN_RENDER:
        monkeypatch.setattr(dotted, _forbidden, raising=False)
    yield reads


def test_construction_reaches_no_filesystem_environment_or_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    page_config: PageConfig,
    tmp_path: Path,
) -> None:
    """Building a generator resolves no path and starts no Mermaid process.

    Both forms are built: one that supplies a template directory and one that
    takes the shipped default. Neither may resolve, stat or read anything, so
    the default must already be resolved when the module loads.
    """
    page = dc.replace(page_config, output_dir=tmp_path / "out")
    supplied = tmp_path / "templates"

    with _watched(monkeypatch) as reads:
        explicit = PageContentGenerator(page, templates_dir=supplied)
        defaulted = PageContentGenerator(page)

    assert explicit.templates_dir == supplied, (
        "a supplied template directory must be kept as given"
    )
    assert defaulted.templates_dir == DEFAULT_TEMPLATES_DIR, (
        "an omitted template directory must fall back to the shipped one"
    )
    assert explicit.source.source_url == page.source_url, (
        "construction must resolve the page source without fetching it"
    )
    assert reads == [], f"construction opened {reads!r}"


def test_preparation_needs_no_network_or_rendering(
    monkeypatch: pytest.MonkeyPatch,
    page_config: PageConfig,
    tmp_path: Path,
) -> None:
    """Preparing a document fetches nothing and renders no HTML."""
    page = dc.replace(page_config, output_dir=tmp_path / "out")
    generator = PageContentGenerator(page, fetcher=_forbid_fetch)

    def _forbidden(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Reject any attempt to render a template."""
        msg = "preparing a document must not render"
        raise AssertionError(msg)

    monkeypatch.setattr(generator.env, "render_template", _forbidden)

    prepared = generator.prepare_document("# Guide\n\n## Intro\nBody\n")

    assert [section.title for section in prepared.sections] == ["Intro"]


def test_rendering_reaches_no_filesystem_environment_or_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    page_config: PageConfig,
    tmp_path: Path,
) -> None:
    """A prepared document renders with no read, environment lookup or process."""
    page = dc.replace(page_config, output_dir=tmp_path / "out")
    generator = PageContentGenerator(page, fetcher=_forbid_fetch)
    prepared = generator.prepare_document("# Guide\n\n## Intro\nBody\n")

    with _watched(monkeypatch) as reads:
        document = generator.render_document(
            prepared,
            source_url=page.source_url,
            version_display=None,
            page_description="Fixture description",
            generated_at=BUILD_TIMESTAMP,
        )

    assert document.sections, "the prepared document must still render"
    assert document.sections[0][1], "the rendered section must not be empty"
    assert reads == [], f"rendering opened {reads!r}"


def test_a_render_failure_names_the_bundle_and_is_raised(
    page_config: PageConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing worker reports its page key before the error escapes."""
    pages = [
        dc.replace(page_config, key=key, output_dir=tmp_path / key)
        for key in ("good", "bad")
    ]

    def render(generator: PageContentGenerator) -> RenderedDocument:
        """Fail for one bundle so the writer's error path runs."""
        if generator.page.key == "bad":
            msg = "upstream document is unreadable"
            raise RuntimeError(msg)
        return RenderedDocument(
            generator.page.output_dir,
            generator.page.output_dir / "metadata.json",
            [("page.html", "ok")],
        )

    monkeypatch.setattr(PageContentGenerator, "render", render)

    with (
        caplog.at_level(logging.ERROR, logger="df12_pages.cli"),
        pytest.raises(RuntimeError, match="upstream document is unreadable"),
    ):
        list(_write_documents(pages, 1))

    assert "document bundle 'bad' failed to render" in caplog.text


def test_render_writes_nothing_until_the_document_is_published(
    page_config: PageConfig,
    markdown_response: MarkdownResponseState,
    tmp_path: Path,
) -> None:
    """Rendering publishes nothing: the output dir waits until write()."""
    # A directory of this test's own: ``page_config`` is module-scoped, and the
    # other tests in the module have already published into its directory.
    fresh = dc.replace(page_config, output_dir=tmp_path / "unpublished")
    generator = PageContentGenerator(fresh)

    document = generator.render()

    assert not fresh.output_dir.exists(), "render() must not create the output dir"
    assert document.sections, "render() must produce the sections to publish"

    written = document.write()

    assert written.html_paths, "write() must publish the rendered sections"
    assert written.metadata_written, "write() must publish the index pointer"
    assert all(path.exists() for path in written.html_paths)


def _forbid_fetch(
    source: DocumentSource, *, updated_at: dt.datetime | None = None
) -> FetchedMarkdown:
    """Fail on use, proving the path under test reaches no network."""
    msg = f"no document should be fetched from {source.source_url!r}"
    raise AssertionError(msg)


class _UnusedMermaid(MermaidRenderer):
    """Fail on use, proving the path under test compiles no diagram."""

    def render(self, source: str) -> str | None:
        """Reject any attempt to start the Mermaid CLI."""
        msg = f"no diagram should be compiled from {source!r}"
        raise AssertionError(msg)


def test_render_document_renders_prepared_markdown_without_publishing(
    page_config: PageConfig,
    sample_markdown: str,
    tmp_path: Path,
) -> None:
    """Preparation and rendering take values: no fetch and no output write."""
    output_dir = tmp_path / "unpublished"
    generator = PageContentGenerator(
        page_config,
        output_dir=output_dir,
        fetcher=_forbid_fetch,
        mermaid=_UnusedMermaid(),
    )

    prepared = generator.prepare_document(sample_markdown)
    document = generator.render_document(
        prepared,
        source_url=page_config.source_url,
        version_display=None,
        page_description="Fixture description",
        generated_at=BUILD_TIMESTAMP,
    )

    assert document.sections, "the fixture must render at least one section"
    assert document.output_dir == output_dir
    assert not output_dir.exists(), "render_document() must not touch the disk"


def test_render_document_reads_no_file_once_the_document_is_prepared(
    page_config: PageConfig,
    sample_markdown: str,
    tmp_path: Path,
) -> None:
    """Rendering stays possible after its templates are gone, so it reads none."""
    templates = tmp_path / "templates"
    shutil.copytree(REPO_ROOT / "df12_pages" / "templates", templates)
    generator = PageContentGenerator(
        page_config, templates_dir=templates, output_dir=tmp_path / "unpublished"
    )

    prepared = generator.prepare_document(sample_markdown)
    shutil.rmtree(templates)
    document = generator.render_document(
        prepared,
        source_url=page_config.source_url,
        version_display=None,
        page_description="Fixture description",
        generated_at=BUILD_TIMESTAMP,
    )

    assert document.sections, "a prepared document must still render its sections"
    assert all(html for _name, html in document.sections), (
        "every prepared section must render non-empty HTML without its templates"
    )


def test_publish_documents_runs_only_the_injected_render(
    page_config: PageConfig, sample_markdown: str, tmp_path: Path
) -> None:
    """The writer schedules the caller's render and fetches nothing itself."""
    keys = ["first", "second"]
    pages = [
        dc.replace(page_config, key=key, output_dir=tmp_path / key) for key in keys
    ]
    rendered: list[str] = []

    def render(page: PageConfig) -> RenderedDocument:
        """Render a fixture with fetching forbidden and record the bundle."""
        generator = PageContentGenerator(
            page, fetcher=_forbid_fetch, mermaid=_UnusedMermaid()
        )
        rendered.append(page.key)
        prepared = generator.prepare_document(sample_markdown)
        return generator.render_document(
            prepared,
            source_url=page.source_url,
            version_display=None,
            page_description="Fixture description",
            generated_at=BUILD_TIMESTAMP,
        )

    paths = list(_publish_documents(pages, len(pages), render))

    assert sorted(rendered) == keys, "each bundle must be rendered exactly once"
    per_bundle = len(paths) // len(pages)
    assert per_bundle >= 1, "each bundle must publish at least one section"
    assert len(paths) == per_bundle * len(pages), (
        f"expected each bundle's paths to be contiguous, got {paths!r}"
    )
    for index, page in enumerate(pages):
        group = paths[index * per_bundle : (index + 1) * per_bundle]
        assert {path.parent for path in group} == {page.output_dir}, (
            "publication must stay in configuration order"
        )
        metadata = page.output_dir / PAGE_META_TEMPLATE.format(key=page.key)
        assert json.loads(metadata.read_text()) == {"first_file": group[0].name}


def test_document_workers_publish_overlaps_in_order(
    page_config: PageConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The later bundle still wins a shared path when it finishes first."""
    _stub_render_in_order(monkeypatch, reverse_completion=True)
    pages = [
        dc.replace(page_config, key=key, output_dir=tmp_path)
        for key in ("first", "second")
    ]
    paths = list(_write_documents(pages, 2))
    assert paths == [tmp_path / "docs-test-shared-heading.html"] * 2
    assert "Content from second." in paths[0].read_text()
    for page in pages:
        metadata = tmp_path / PAGE_META_TEMPLATE.format(key=page.key)
        assert json.loads(metadata.read_text()) == {"first_file": paths[0].name}


def test_rendered_document_without_sections_writes_no_metadata(
    tmp_path: Path,
) -> None:
    """An empty bundle publishes no files and therefore no index pointer."""
    metadata_path = tmp_path / "metadata.json"

    written = RenderedDocument(tmp_path, metadata_path, []).write()

    assert written == WrittenDocument(
        html_paths=[], metadata_path=metadata_path, metadata_written=False
    ), "an empty bundle writes no HTML and reports no metadata pointer"
    assert not metadata_path.exists(), "an empty bundle must not claim a first file"


def test_rendered_document_reports_an_unwritable_metadata_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A metadata failure is visible in the result and must not fail the HTML."""
    metadata_path = tmp_path / "metadata"
    metadata_path.mkdir()
    document = RenderedDocument(tmp_path, metadata_path, [("page.html", "<p>ok</p>")])

    written = document.write()

    assert written.html_paths == [tmp_path / "page.html"]
    assert written.html_paths[0].read_text() == "<p>ok</p>"
    assert written.metadata_path == metadata_path, (
        "the result must name the destination it could not write"
    )
    assert not written.metadata_written, "the failed pointer must be reported"
    assert isinstance(written.metadata_error, OSError), (
        "the result must carry the error that stopped the pointer"
    )
    assert caplog.records == [], "write() reports through its result, not the log"

    with caplog.at_level(logging.WARNING):
        published = publish_document(document)

    assert published == written.html_paths
    assert "could not write document metadata" in caplog.text


def _record_generated_workers(
    monkeypatch: pytest.MonkeyPatch, site_config: object
) -> list[int]:
    """Capture the worker counts that reach the shared document writer."""
    recorded: list[int] = []
    monkeypatch.setattr(cli, "load_site_config", lambda _path: site_config)

    def record_workers(
        pages: list[PageConfig], workers: int, **_kwargs: object
    ) -> typ.Iterator[Path]:
        """Record the worker count and write nothing."""
        recorded.append(workers)
        return iter(())

    monkeypatch.setattr(cli, "_write_documents", record_workers)
    return recorded


def test_generate_forwards_doc_workers_to_the_main_site(
    page_config: PageConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The main-site path receives the configured worker count."""
    page = dc.replace(page_config, key="main-page", output_dir=tmp_path)
    site_config = SimpleNamespace(
        pages={"main-page": page},
        sites={},
        docs_index_output=None,
        get_page=lambda key: {"main-page": page}[key],
    )
    recorded = _record_generated_workers(monkeypatch, site_config)

    generate(page="main-page", doc_workers=3)

    assert recorded == [3]


def test_generate_forwards_doc_workers_to_a_subsite(
    page_config: PageConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sub-site path receives the configured worker count."""
    page = dc.replace(page_config, key="sub-page", output_dir=tmp_path)
    subsite = SimpleNamespace(
        key="sub", templates_dir=tmp_path, pages={"sub-page": page}
    )
    site_config = SimpleNamespace(pages={}, sites={"sub": subsite})
    recorded = _record_generated_workers(monkeypatch, site_config)

    generate(site="sub", page="sub-page", doc_workers=5)

    assert recorded == [5]


# Cyclopts warns whenever it is called without explicit tokens under pytest;
# ``main`` deliberately parses ``sys.argv`` and has no tokens to pass.
@pytest.mark.filterwarnings(
    "ignore:Cyclopts application invoked without tokens:UserWarning"
)
def test_pages_command_rejects_zero_doc_workers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The console entry point exits non-zero with the usage error."""
    monkeypatch.setattr(sys, "argv", ["pages", "generate", "--doc-workers", "0"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1, "a usage error must exit with status 1"
    assert "--doc-workers must be at least one" in capsys.readouterr().err


def test_generate_rejects_zero_document_workers() -> None:
    """Reject an invalid pool size before doing any build work."""
    with pytest.raises(ValueError, match="--doc-workers must be at least one"):
        generate(doc_workers=0)
