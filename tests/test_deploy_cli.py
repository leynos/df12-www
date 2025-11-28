from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from df12_pages import deploy


def test_credentials_round_trip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    creds = deploy.resolve_credentials(
        config_path=config_path,
        aws_access_key_id="AKIA_TEST",
        aws_secret_access_key="SECRET",
        scw_access_key="SCWKEY",
        scw_secret_key="SCWSECRET",
        cloudflare_api_token="cf-token",
        github_token="gh-token",
        region="fr-par",
        s3_endpoint="https://s3.fr-par.scw.cloud",
        save=True,
    )
    assert config_path.exists()
    loaded = deploy.resolve_credentials(config_path=config_path, save=False)
    assert loaded.aws_access_key_id == creds.aws_access_key_id
    assert loaded.aws_secret_access_key == creds.aws_secret_access_key
    assert loaded.region == "fr-par"
    assert loaded.s3_endpoint == "https://s3.fr-par.scw.cloud"


def test_build_env_sets_expected_keys() -> None:
    creds = deploy.CredentialSet(
        aws_access_key_id="AKIA_TEST",
        aws_secret_access_key="SECRET",
        scw_access_key="SCWKEY",
        scw_secret_key="SCWSECRET",
        cloudflare_api_token="cf-token",
        github_token="gh-token",
        region="fr-par",
        s3_endpoint="https://s3.fr-par.scw.cloud",
    )
    env = deploy.build_env(creds)
    assert env["AWS_ACCESS_KEY_ID"] == "AKIA_TEST"
    assert env["AWS_SECRET_ACCESS_KEY"] == "SECRET"
    assert env["TF_VAR_scaleway_access_key"] == "SCWKEY"
    assert env["TF_VAR_scaleway_secret_key"] == "SCWSECRET"
    assert env["CLOUDFLARE_API_TOKEN"] == "cf-token"
    assert env["TF_VAR_cloudflare_api_token"] == "cf-token"
    assert env["GITHUB_TOKEN"] == "gh-token"
    assert env["AWS_DEFAULT_REGION"] == "fr-par"
    assert env["AWS_S3_ENDPOINT"] == "https://s3.fr-par.scw.cloud"


def test_backend_config_parses_tfbackend(tmp_path: Path) -> None:
    backend_path = tmp_path / "backend.tfbackend"
    backend_path.write_text(
        'bucket = "df12-test"\n'
        'region = "fr-par"\n'
        'endpoints = { s3 = "https://s3.fr-par.scw.cloud" }\n',
        encoding="utf-8",
    )
    backend = deploy.BackendConfig.from_file(backend_path)
    assert backend.bucket == "df12-test"
    assert backend.region == "fr-par"
    assert backend.endpoint == "https://s3.fr-par.scw.cloud"


def test_ensure_backend_bucket_creates_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = deploy.BackendConfig(
        bucket="df12-test", region="fr-par", endpoint="https://s3.fr-par.scw.cloud"
    )
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, env: dict[str, str], text: bool, capture_output: bool):
        calls.append(cmd)
        if "head-bucket" in cmd:
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    deploy.ensure_backend_bucket(
        backend,
        env={"AWS_ACCESS_KEY_ID": "AKIA", "AWS_SECRET_ACCESS_KEY": "SECRET"},
        aws_exe="/usr/bin/aws",
    )
    assert any("head-bucket" in call for call in calls)
    assert any("create-bucket" in call for call in calls)


def _write_backend(tmp_path: Path) -> Path:
    path = tmp_path / "backend.tfbackend"
    path.write_text(
        'bucket = "df12-test"\n'
        'region = "fr-par"\n'
        'endpoints = { s3 = "https://s3.fr-par.scw.cloud" }\n',
        encoding="utf-8",
    )
    return path


def test_init_stack_runs_init(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backend_path = _write_backend(tmp_path)
    var_file = tmp_path / "terraform.tfvars"
    var_file.write_text('cloud_provider = "scaleway"\n', encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(deploy, "ensure_backend_bucket", lambda *args, **kwargs: calls.append(["ensure"]))

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)
    creds = deploy.CredentialSet(
        aws_access_key_id="AKIA",
        aws_secret_access_key="SECRET",
        cloudflare_api_token="cf",
        github_token="gh",
        scw_access_key="SCW",
        scw_secret_key="SCWSECRET",
        region="fr-par",
        s3_endpoint="https://s3.fr-par.scw.cloud",
    )
    deploy.init_stack(
        var_file=var_file,
        backend_config=backend_path,
        credentials=creds,
        save_credentials_flag=False,
    )
    assert calls[0] == ["ensure"]
    assert ["init", "-backend-config", str(backend_path), "-var-file", str(var_file)] in calls


def test_plan_stack_runs_init_and_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backend_path = _write_backend(tmp_path)
    var_file = tmp_path / "terraform.tfvars"
    var_file.write_text('cloud_provider = "scaleway"\n', encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(deploy, "ensure_backend_bucket", lambda *args, **kwargs: calls.append(["ensure"]))

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)
    creds = deploy.CredentialSet(
        aws_access_key_id="AKIA",
        aws_secret_access_key="SECRET",
        scw_access_key="SCW",
        scw_secret_key="SCWSECRET",
        region="fr-par",
    )
    deploy.plan_stack(
        var_file=var_file,
        backend_config=backend_path,
        plan_file=tmp_path / "plan.out",
        credentials=creds,
        save_credentials_flag=False,
    )
    assert calls[0] == ["ensure"]
    assert ["init", "-backend-config", str(backend_path), "-var-file", str(var_file)] in calls
    assert ["plan", "-var-file", str(var_file), "-out", str(tmp_path / "plan.out")] in calls


def test_apply_stack_uses_plan_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    backend_path = _write_backend(tmp_path)
    var_file = tmp_path / "terraform.tfvars"
    var_file.write_text('cloud_provider = "scaleway"\n', encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(deploy, "ensure_backend_bucket", lambda *args, **kwargs: calls.append(["ensure"]))

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)
    creds = deploy.CredentialSet(
        aws_access_key_id="AKIA",
        aws_secret_access_key="SECRET",
        region="fr-par",
    )
    plan_file = tmp_path / "plan.out"
    deploy.apply_stack(
        var_file=var_file,
        backend_config=backend_path,
        plan_file=plan_file,
        credentials=creds,
        save_credentials_flag=False,
    )
    assert calls[0] == ["ensure"]
    assert ["init", "-backend-config", str(backend_path), "-var-file", str(var_file)] in calls
    assert ["apply", str(plan_file)] in calls
