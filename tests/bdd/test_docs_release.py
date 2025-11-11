"""Behaviour tests for rendering documentation from release tags."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests
from betamax import Betamax
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

from df12_pages.config import load_site_config
from df12_pages.generator import PageContentGenerator

FEATURE_FILE = Path(__file__).resolve().parents[2] / "features" / "docs_release.feature"
scenarios(FEATURE_FILE)


@pytest.fixture
def scenario_state() -> dict[str, object]:
    return {}


@given("a docs config referencing a release-tagged repo")
def given_release_config(tmp_path: Path, scenario_state: dict[str, object]) -> None:
    output_dir = tmp_path / "docs"
    output_dir.mkdir()
    config_path = tmp_path / "pages.yaml"
    config_path.write_text(
        f"""
defaults:
  output_dir: {output_dir}
  branch: main
  doc_path: README.md
pages:
  requests-docs:
    label: Requests Docs
    repo: psf/requests
    doc_path: README.md
    latest_release: v2.32.5
    latest_release_published_at: 2025-08-19T05:41:32Z
    description: HTTP for Humans
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    scenario_state["config_path"] = config_path
    scenario_state["output_dir"] = output_dir


@given("documentation fetches are replayed via betamax")
def given_betamax_session(scenario_state: dict[str, object], tmp_path: Path) -> None:
    session = requests.Session()
    cassette_dir = Path(__file__).resolve().parents[1] / "cassettes"
    recorder = Betamax(
        session,
        cassette_library_dir=str(cassette_dir),
        default_cassette_options={"record_mode": "once"},
    )
    scenario_state["session"] = session
    scenario_state["recorder"] = recorder


@when("I render the docs for that page")
def when_render_docs(
    scenario_state: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_site_config(scenario_state["config_path"])
    page = config.get_page("requests-docs")
    output_dir = scenario_state["output_dir"]
    session = scenario_state["session"]
    recorder = scenario_state["recorder"]
    calls: list[str] = []

    def session_get(url: str, timeout: int = 30):  # noqa: ARG001
        calls.append(url)
        return session.get(url, timeout=timeout)

    monkeypatch.setattr("df12_pages.generator.requests.get", session_get)

    generator = PageContentGenerator(page, output_dir=output_dir)
    with recorder.use_cassette("docs_release/render"):
        written = generator.run()

    scenario_state["written"] = written
    scenario_state["calls"] = calls


@then("the HTML shows the release version and tag date")
def then_release_metadata_present(scenario_state: dict[str, object]) -> None:
    written: list[Path] = scenario_state["written"]
    html = written[0].read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    meta_items = [
        span.get_text(strip=True) for span in soup.select(".doc-meta-list__item")
    ]
    assert meta_items == ["Version 2.32.5", "Updated Aug 19, 2025"]

    eyebrow = soup.select_one(".doc-sidebar__eyebrow")
    body = soup.select_one(".doc-sidebar__body")
    assert eyebrow is not None and eyebrow.get_text(strip=True) == "Requests Docs"
    assert body is not None and body.get_text(strip=True) == "HTTP for Humans"

    calls: list[str] = scenario_state["calls"]
    assert any("refs/tags/v2.32.5" in url for url in calls)
