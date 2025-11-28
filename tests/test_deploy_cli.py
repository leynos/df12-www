from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from df12_pages import deploy


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[auth]
aws_access_key_id = "AKIA_CFG"
aws_secret_access_key = "SECRET_CFG"
cloudflare_api_token = "cf-token"
github_token = "gh-token"
region = "fr-par"
s3_endpoint = "https://s3.fr-par.scw.cloud"

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


def test_credentials_round_trip(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    creds = deploy.resolve_credentials(
        config_path=config_path,
        aws_access_key_id="AKIA_TEST",
        aws_secret_access_key="SECRET",
        scw_access_key="SCWKEY",
        scw_secret_key="SCWSECRET",
        cloudflare_api_token="cf-token-new",
        github_token="gh-token-new",
        save=True,
    )
    loaded = deploy.resolve_credentials(config_path=config_path, save=False)
    assert loaded.aws_access_key_id == creds.aws_access_key_id == "AKIA_TEST"
    assert loaded.aws_secret_access_key == "SECRET"
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


def test_materialize_backend_disables_encrypt_for_scaleway() -> None:
    backend = deploy.BackendConfig(
        bucket="df12-test", region="fr-par", endpoint="https://s3.fr-par.scw.cloud"
    )
    creds = deploy.CredentialSet(aws_access_key_id="AKIA", aws_secret_access_key="SECRET")
    path = deploy._materialize_backend_file(backend, creds)
    try:
        content = path.read_text(encoding="utf-8")
        assert "encrypt = false" in content
        assert "access_key = \"AKIA\"" in content
        assert "secret_key = \"SECRET\"" in content
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600
    finally:
        path.unlink(missing_ok=True)


def test_materialize_tfvars_merges_creds() -> None:
    site = {"domain_name": "example.com", "cloud_provider": "scaleway"}
    creds = deploy.CredentialSet(
        scw_access_key="SCW",
        scw_secret_key="SCWSECRET",
        cloudflare_api_token="cf-token",
        github_token="gh-token",
        region="fr-par",
        s3_endpoint="https://s3.fr-par.scw.cloud",
    )
    path = deploy._materialize_tfvars(site, creds)
    try:
        text = path.read_text(encoding="utf-8")
        assert "cloudflare_api_token = \"cf-token\"" in text
        assert "github_token = \"gh-token\"" in text
        assert "scaleway_access_key = \"SCW\"" in text
        assert "scaleway_secret_key = \"SCWSECRET\"" in text
        assert "scaleway_region = \"fr-par\"" in text
        mode = os.stat(path).st_mode & 0o777
        assert mode == 0o600
    finally:
        path.unlink(missing_ok=True)


def test_resolve_credentials_falls_back_to_backend_region(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    creds = deploy.resolve_credentials(config_path=config_path, save=False)
    assert creds.region == "fr-par"


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


def test_ensure_backend_bucket_uses_env_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = deploy.BackendConfig(bucket="df12-test", region="fr-par", endpoint=None)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, env: dict[str, str], text: bool, capture_output: bool):
        calls.append(cmd)
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        deploy.ensure_backend_bucket(
            backend,
            env={"AWS_ACCESS_KEY_ID": "AKIA", "AWS_SECRET_ACCESS_KEY": "SECRET", "AWS_S3_ENDPOINT": "https://s3.fr-par.scw.cloud"},
            aws_exe="/usr/bin/aws",
        )
    assert any("--endpoint-url" in call for call in calls)


def test_init_stack_runs_init(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(deploy, "ensure_backend_bucket", lambda *args, **kwargs: calls.append(["ensure"]))

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)

    deploy.init_stack(config_path=config_path, save_credentials_flag=False)

    init_call = next(call for call in calls if call and call[0] == "init")
    backend_path = Path(init_call[init_call.index("-backend-config") + 1])
    tfvars_path = Path(init_call[init_call.index("-var-file") + 1])

    assert calls[0] == ["ensure"]
    assert not backend_path.exists()
    assert not tfvars_path.exists()


def test_plan_stack_runs_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(deploy, "ensure_backend_bucket", lambda *args, **kwargs: calls.append(["ensure"]))

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)

    plan_file = tmp_path / "plan.out"
    deploy.plan_stack(
        config_path=config_path,
        plan_file=plan_file,
        save_credentials_flag=False,
    )

    init_call = next(call for call in calls if call and call[0] == "init")
    plan_call = next(call for call in calls if call and call[0] == "plan")
    backend_path = Path(init_call[init_call.index("-backend-config") + 1])
    tfvars_path = Path(init_call[init_call.index("-var-file") + 1])

    assert calls[0] == ["ensure"]
    assert plan_call[-1] == str(plan_file)
    assert not backend_path.exists()
    assert not tfvars_path.exists()


def test_apply_stack_uses_plan_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(deploy, "ensure_backend_bucket", lambda *args, **kwargs: calls.append(["ensure"]))

    def fake_run(args: list[str], env: dict[str, str]):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)

    plan_file = tmp_path / "plan.out"
    deploy.apply_stack(
        config_path=config_path,
        plan_file=plan_file,
        save_credentials_flag=False,
    )

    init_call = next(call for call in calls if call and call[0] == "init")
    apply_call = next(call for call in calls if call and call[0] == "apply")
    backend_path = Path(init_call[init_call.index("-backend-config") + 1])
    tfvars_path = Path(init_call[init_call.index("-var-file") + 1])

    assert calls[0] == ["ensure"]
    assert apply_call[1] == str(plan_file)
    assert not backend_path.exists()
    assert not tfvars_path.exists()
