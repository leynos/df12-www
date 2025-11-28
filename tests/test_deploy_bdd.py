from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_bdd import given, scenarios, then, when

from df12_pages import deploy

scenarios("../features/deploy_config.feature")


@pytest.fixture()
def context() -> dict[str, object]:
    return {}


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[auth]
aws_access_key_id = "AKIA_CFG"
aws_secret_access_key = "SECRET_CFG"
cloudflare_api_token = "cf-token"
github_token = "gh-token"

[backend]
bucket = "df12-test"
region = "fr-par"
endpoint = "https://s3.fr-par.scw.cloud"

[site]
domain_name = "example.com"
root_domain = "example.com"
environment = "dev"
project_name = "df12-www"
cloud_provider = "scaleway"
cloudflare_zone_id = "0123456789abcdef0123456789abcdef"
cloudflare_proxied = true
scaleway_project_id = "11111111-2222-3333-4444-555555555555"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


@given("a deploy config file with backend and site values")
def a_deploy_config_file_with_backend_and_site_values(tmp_path: Path, context: dict[str, object]) -> None:
    context["config_path"] = _write_config(tmp_path)


@when("I initialise the stack with the config")
def i_initialise_the_stack_with_the_config(monkeypatch: pytest.MonkeyPatch, context: dict[str, object]) -> None:
    calls: list[list[str]] = []

    def fake_ensure(*args, **kwargs):
        calls.append(["ensure"])

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        context["backend_path"] = Path(args[args.index("-backend-config") + 1])
        context["tfvars_path"] = Path(args[args.index("-var-file") + 1])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "ensure_backend_bucket", fake_ensure)
    monkeypatch.setattr(deploy, "run_tofu", fake_run)

    deploy.init_stack(config_path=context["config_path"], save_credentials_flag=False)

    context["calls"] = calls


@then("a temporary backend file is passed to tofu init")
def a_temporary_backend_file_is_passed_to_tofu_init(context: dict[str, object]) -> None:
    backend_path = context["backend_path"]
    assert isinstance(backend_path, Path)
    assert backend_path.name.startswith("df12-backend-")
    assert backend_path.suffix == ".tfbackend"
    assert not backend_path.exists()


@then("a temporary tfvars file is passed to tofu init")
def a_temporary_tfvars_file_is_passed_to_tofu_init(context: dict[str, object]) -> None:
    tfvars_path = context["tfvars_path"]
    assert isinstance(tfvars_path, Path)
    assert tfvars_path.name.startswith("df12-vars-")
    assert tfvars_path.suffix == ".tfvars"
    assert not tfvars_path.exists()
