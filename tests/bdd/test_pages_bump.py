"""Behaviour tests for the ``pages bump`` command using pytest-bdd."""

from __future__ import annotations

import typing as typ
from pathlib import Path
from textwrap import dedent

import pytest
import requests
from betamax import Betamax
from pytest_bdd import given, scenarios, then, when
from ruamel.yaml import YAML

from df12_pages.bump import bump_latest_release_metadata
from df12_pages.releases import GitHubReleaseClient, ReleaseInfo

FEATURE_FILE = Path(__file__).resolve().parents[2] / "features" / "pages_bump.feature"
scenarios(FEATURE_FILE)

EXPECTED_TAGS: dict[str, str] = {
    "requests": "v2.32.5",
    "flask": "3.1.2",
}

ScenarioState = dict[str, typ.Any]


@pytest.fixture(scope="session")
def cassette_dir() -> Path:
    """Return the directory where Betamax cassettes are stored for this test suite."""
    path = Path(__file__).resolve().parents[1] / "cassettes"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def scenario_state() -> ScenarioState:
    """Return a mutable dict used to share scenario state across BDD steps."""
    return {}


@given("a pages config referencing public repositories")
def given_pages_config(tmp_path: Path, scenario_state: ScenarioState) -> None:
    """Write a pages.yaml config that references multiple public repositories."""
    config_path = tmp_path / "pages.yaml"
    config_path.write_text(
        dedent(
            """
            defaults:
              output_dir: public
            pages:
              requests:
                label: Requests API Docs
                repo: psf/requests
              flask:
                label: Flask Docs
                repo: pallets/flask
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    scenario_state["config_path"] = config_path


@given("GitHub responses are replayed via betamax")
def given_betamax(scenario_state: ScenarioState, cassette_dir: Path) -> None:
    """Configure a Betamax-backed session to replay GitHub API responses."""
    session = requests.Session()
    recorder = Betamax(
        session,
        cassette_library_dir=str(cassette_dir),
        default_cassette_options={"record_mode": "once"},
    )
    scenario_state["session"] = session
    scenario_state["recorder"] = recorder


@when("I run the pages bump workflow")
def when_run_bump(scenario_state: ScenarioState) -> None:
    """Execute the pages bump workflow using the configured GitHub client."""
    config_path = typ.cast("Path", scenario_state["config_path"])
    session = typ.cast("requests.Session", scenario_state["session"])
    recorder = typ.cast("Betamax", scenario_state["recorder"])
    client = GitHubReleaseClient(session=session)

    cassette_name = "pages_bump/latest_release_tags"
    with recorder.use_cassette(cassette_name):
        result = bump_latest_release_metadata(config_path=config_path, client=client)

    scenario_state["result"] = result


@then("the config records the expected release tags")
def then_config_records_expected(scenario_state: ScenarioState) -> None:
    """Verify the pages config and results capture the expected release tags."""
    config_path = typ.cast("Path", scenario_state["config_path"])
    result = typ.cast("dict[str, ReleaseInfo | None]", scenario_state["result"])

    yaml = YAML(typ="safe")
    parsed = yaml.load(config_path.read_text(encoding="utf-8"))

    for page, expected_tag in EXPECTED_TAGS.items():
        release = result[page]
        assert release is not None
        assert release.tag_name == expected_tag
        assert parsed["pages"][page]["latest_release"] == expected_tag
        assert "latest_release_published_at" in parsed["pages"][page]
