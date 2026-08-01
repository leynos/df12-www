"""Unit tests for the deploy CLI credential and stack management."""

from __future__ import annotations

import json
import subprocess
import sys
import typing as typ
from pathlib import Path
from types import SimpleNamespace

import pytest

from df12_pages import cli, deploy

_EXPECTED_FILE_MODE = 0o600
_TOFU_FAILURE_STATUS = 42
_AWS_FAILURE_STATUS = 255


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


_STALE_LOCAL_BACKEND_CACHE: dict[str, object] = {
    "version": 3,
    "backend": {"type": "local", "config": {"path": None, "workspace_dir": None}},
    "modules": [{"path": ["root"], "outputs": {}, "resources": {}, "depends_on": []}],
}


def _write_backend_cache(root: Path, record: dict[str, object] | str) -> None:
    cache_dir = root / ".terraform"
    cache_dir.mkdir(exist_ok=True)
    text = record if isinstance(record, str) else json.dumps(record)
    (cache_dir / "terraform.tfstate").write_text(text, encoding="utf-8")


def test_credentials_round_trip(tmp_path: Path) -> None:
    """Test that credentials can be saved and loaded round-trip."""
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
    assert loaded.aws_secret_access_key == "SECRET"  # noqa: S105
    assert loaded.region == "fr-par"
    assert loaded.s3_endpoint == "https://s3.fr-par.scw.cloud"


def test_build_env_sets_expected_keys() -> None:
    """Test that build_env sets expected environment variable keys."""
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
    assert env["AWS_SECRET_ACCESS_KEY"] == "SECRET"  # noqa: S105
    assert env["TF_VAR_scaleway_access_key"] == "SCWKEY"
    assert env["TF_VAR_scaleway_secret_key"] == "SCWSECRET"  # noqa: S105
    assert env["CLOUDFLARE_API_TOKEN"] == "cf-token"  # noqa: S105
    assert env["TF_VAR_cloudflare_api_token"] == "cf-token"  # noqa: S105
    assert env["GITHUB_TOKEN"] == "gh-token"  # noqa: S105
    assert env["AWS_DEFAULT_REGION"] == "fr-par"
    assert env["AWS_S3_ENDPOINT"] == "https://s3.fr-par.scw.cloud"


def test_materialize_backend_disables_encrypt_for_scaleway() -> None:
    """Test that backend file disables encryption for Scaleway."""
    backend = deploy.BackendConfig(
        bucket="df12-test", region="fr-par", endpoint="https://s3.fr-par.scw.cloud"
    )
    creds = deploy.CredentialSet(
        aws_access_key_id="AKIA", aws_secret_access_key="SECRET"
    )
    path = deploy._materialize_backend_file(backend, creds)
    try:
        content = path.read_text(encoding="utf-8")
        assert "encrypt = false" in content
        assert 'access_key = "AKIA"' in content
        assert 'secret_key = "SECRET"' in content
        mode = path.stat().st_mode & 0o777
        assert mode == _EXPECTED_FILE_MODE
    finally:
        path.unlink(missing_ok=True)


def test_materialize_tfvars_merges_creds() -> None:
    """Test that tfvars file merges credentials correctly."""
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
        assert 'cloudflare_api_token = "cf-token"' in text
        assert 'github_token = "gh-token"' in text
        assert 'scaleway_access_key = "SCW"' in text
        assert 'scaleway_secret_key = "SCWSECRET"' in text
        assert 'scaleway_region = "fr-par"' in text
        mode = path.stat().st_mode & 0o777
        assert mode == _EXPECTED_FILE_MODE
    finally:
        path.unlink(missing_ok=True)


def test_resolve_credentials_falls_back_to_backend_region(tmp_path: Path) -> None:
    """Test that credentials resolution falls back to backend region."""
    config_path = _write_config(tmp_path)
    creds = deploy.resolve_credentials(config_path=config_path, save=False)
    assert creds.region == "fr-par"


def test_ensure_backend_bucket_creates_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that ensure_backend_bucket creates bucket when missing."""
    backend = deploy.BackendConfig(
        bucket="df12-test", region="fr-par", endpoint="https://s3.fr-par.scw.cloud"
    )
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        *,
        check: bool,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
    ) -> SimpleNamespace:
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


def test_ensure_backend_bucket_uses_env_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that ensure_backend_bucket uses environment endpoint."""
    backend = deploy.BackendConfig(bucket="df12-test", region="fr-par", endpoint=None)
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        *,
        check: bool,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
    ) -> typ.Never:
        calls.append(cmd)
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(deploy.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        deploy.ensure_backend_bucket(
            backend,
            env={
                "AWS_ACCESS_KEY_ID": "AKIA",
                "AWS_SECRET_ACCESS_KEY": "SECRET",
                "AWS_S3_ENDPOINT": "https://s3.fr-par.scw.cloud",
            },
            aws_exe="/usr/bin/aws",
        )
    assert any("--endpoint-url" in call for call in calls)


def test_init_stack_runs_init(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that init_stack runs terraform init."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(
        deploy,
        "ensure_backend_bucket",
        lambda *args, **kwargs: calls.append(["ensure"]),
    )

    def fake_run(args: list[str], env: dict[str, str]) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)

    deploy.init_stack(config_path=config_path, save_credentials_flag=False)

    init_call = next(call for call in calls if call and call[0] == "init")
    backend_path = Path(init_call[init_call.index("-backend-config") + 1])
    tfvars_path = Path(init_call[init_call.index("-var-file") + 1])

    assert calls[0] == ["ensure"], "backend bucket must be ensured before tofu runs"
    assert "-reconfigure" not in init_call, (
        "plain init must not discard a trusted backend cache"
    )
    assert not backend_path.exists(), "temporary backend file must be cleaned up"
    assert not tfvars_path.exists(), "temporary tfvars file must be cleaned up"


def test_init_stack_reconfigures_stale_local_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test that init discards a provably stale local backend cache."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    _write_backend_cache(tmp_path, _STALE_LOCAL_BACKEND_CACHE)
    calls: list[list[str]] = []

    monkeypatch.setattr(
        deploy,
        "ensure_backend_bucket",
        lambda *args, **kwargs: calls.append(["ensure"]),
    )

    def fake_run(args: list[str], env: dict[str, str]) -> SimpleNamespace:
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_tofu", fake_run)

    deploy.init_stack(config_path=config_path, save_credentials_flag=False)

    init_call = next(call for call in calls if call and call[0] == "init")
    assert "-reconfigure" in init_call, (
        "a stale empty local backend cache must be discarded via -reconfigure"
    )


def test_cached_backend_discardable_for_stale_local_record(tmp_path: Path) -> None:
    """Test that an empty local backend cache is judged discardable."""
    _write_backend_cache(tmp_path, _STALE_LOCAL_BACKEND_CACHE)
    assert deploy._cached_backend_is_discardable(tmp_path), (
        "an empty local backend cache with no local state must be discardable"
    )


def test_cached_backend_discardable_despite_empty_local_state(tmp_path: Path) -> None:
    """Test that an empty root state file does not block discarding."""
    _write_backend_cache(tmp_path, _STALE_LOCAL_BACKEND_CACHE)
    (tmp_path / "terraform.tfstate").write_text(
        json.dumps({"version": 4, "resources": []}), encoding="utf-8"
    )
    assert deploy._cached_backend_is_discardable(tmp_path), (
        "a resource-free local state file must not block discarding"
    )


def test_cached_backend_absent_is_not_discardable(tmp_path: Path) -> None:
    """Test that a missing cache never triggers -reconfigure."""
    assert not deploy._cached_backend_is_discardable(tmp_path), (
        "without a cached record plain init suffices"
    )


def test_cached_backend_kept_when_local_state_has_resources(tmp_path: Path) -> None:
    """Test that real local state blocks discarding the cache."""
    _write_backend_cache(tmp_path, _STALE_LOCAL_BACKEND_CACHE)
    (tmp_path / "terraform.tfstate").write_text(
        json.dumps({"version": 4, "resources": [{"type": "scaleway_bucket"}]}),
        encoding="utf-8",
    )
    assert not deploy._cached_backend_is_discardable(tmp_path), (
        "local state holding resources must keep the migration safety check"
    )


@pytest.mark.parametrize(
    "record",
    [
        pytest.param(
            {"backend": {"type": "s3", "config": {"bucket": "other"}}},
            id="remote-backend",
        ),
        pytest.param(
            {"backend": {"type": "local", "config": {"path": "custom.tfstate"}}},
            id="custom-state-path",
        ),
        pytest.param(
            {
                "backend": {"type": "local", "config": {"path": None}},
                "modules": [{"resources": {"aws_s3_bucket.site": {}}}],
            },
            id="cached-resources",
        ),
        pytest.param(
            {
                "backend": {"type": "local", "config": {"path": None}},
                "modules": ["bogus"],
            },
            id="malformed-module-entry",
        ),
        pytest.param(
            {
                "backend": {"type": "local", "config": {"path": None}},
                "modules": "bogus",
            },
            id="non-list-modules",
        ),
        pytest.param("not json", id="malformed-cache"),
        pytest.param("[]", id="non-dict-cache"),
    ],
)
def test_cached_backend_kept_for_unsafe_records(
    tmp_path: Path, record: dict[str, object] | str
) -> None:
    """Test that anything but a provably stale local cache keeps tofu's check."""
    _write_backend_cache(tmp_path, record)
    assert not deploy._cached_backend_is_discardable(tmp_path), (
        "only a provably stale local backend cache may be discarded"
    )


def test_plan_stack_runs_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that plan_stack runs terraform plan."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(
        deploy,
        "ensure_backend_bucket",
        lambda *args, **kwargs: calls.append(["ensure"]),
    )

    def fake_run(args: list[str], env: dict[str, str]) -> SimpleNamespace:
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

    assert calls[0] == ["ensure"], "backend bucket must be ensured before tofu runs"
    assert "-reconfigure" not in init_call, (
        "plain init must not discard a trusted backend cache"
    )
    assert plan_call[-1] == str(plan_file), (
        "plan output path must be forwarded to tofu plan"
    )
    assert not backend_path.exists(), "temporary backend file must be cleaned up"
    assert not tfvars_path.exists(), "temporary tfvars file must be cleaned up"


def test_apply_stack_uses_plan_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test that apply_stack uses the plan file."""
    config_path = _write_config(tmp_path)
    monkeypatch.chdir(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(
        deploy,
        "ensure_backend_bucket",
        lambda *args, **kwargs: calls.append(["ensure"]),
    )

    def fake_run(args: list[str], env: dict[str, str]) -> SimpleNamespace:
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

    assert calls[0] == ["ensure"], "backend bucket must be ensured before tofu runs"
    assert "-reconfigure" not in init_call, (
        "plain init must not discard a trusted backend cache"
    )
    assert apply_call[1] == str(plan_file), "apply must consume the supplied plan file"
    assert not backend_path.exists(), "temporary backend file must be cleaned up"
    assert not tfvars_path.exists(), "temporary tfvars file must be cleaned up"


def test_main_reports_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that main maps CalledProcessError to one line and its status."""

    def boom() -> None:
        raise subprocess.CalledProcessError(
            _TOFU_FAILURE_STATUS, ["/usr/sbin/tofu", "init", "-reconfigure"]
        )

    monkeypatch.setattr(cli, "app", boom)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == _TOFU_FAILURE_STATUS, (
        "exit status must preserve the subprocess's return code"
    )
    assert capsys.readouterr().err == (
        f"error: tofu init exited with status {_TOFU_FAILURE_STATUS}\n"
    ), "stderr must be exactly one error line naming the failed command"


def test_main_relays_captured_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that captured subprocess stderr is relayed before the error line."""

    def boom() -> None:
        raise subprocess.CalledProcessError(
            _AWS_FAILURE_STATUS,
            ["/usr/bin/aws", "s3api", "head-bucket"],
            stderr="An error occurred (403) when calling HeadBucket: Forbidden\n",
        )

    monkeypatch.setattr(cli, "app", boom)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == _AWS_FAILURE_STATUS, (
        "exit status must preserve the subprocess's return code"
    )
    assert capsys.readouterr().err == (
        "An error occurred (403) when calling HeadBucket: Forbidden\n"
        f"error: aws s3api exited with status {_AWS_FAILURE_STATUS}\n"
    ), "captured stderr must be relayed, followed by exactly one error line"


def test_main_reports_missing_binary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that main converts FileNotFoundError into a one-line message."""

    def boom() -> None:
        msg = "tofu binary not found on PATH"
        raise FileNotFoundError(msg)

    monkeypatch.setattr(cli, "app", boom)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1, "a missing binary must exit with status 1"
    assert capsys.readouterr().err == "error: tofu binary not found on PATH\n", (
        "stderr must be exactly one error line naming the missing binary"
    )


def test_main_reports_credential_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that main converts CredentialError into a one-line message."""

    def boom() -> None:
        msg = "AWS access key and secret key are required"
        raise deploy.CredentialError(msg)

    monkeypatch.setattr(cli, "app", boom)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1, "a credential error must exit with status 1"
    assert capsys.readouterr().err == (
        "error: AWS access key and secret key are required\n"
    ), "stderr must be exactly one error line stating the credential problem"


def test_pages_apply_failure_via_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test that the console entry point maps a failed apply to clean stderr."""

    def boom(**kwargs: object) -> None:
        raise subprocess.CalledProcessError(
            _TOFU_FAILURE_STATUS, ["/usr/sbin/tofu", "apply"]
        )

    monkeypatch.setattr(cli, "apply_stack", boom)
    monkeypatch.setattr(sys, "argv", ["pages", "apply"])

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == _TOFU_FAILURE_STATUS, (
        "exit status must preserve the subprocess's return code"
    )
    assert capsys.readouterr().err == (
        f"error: tofu apply exited with status {_TOFU_FAILURE_STATUS}\n"
    ), "stderr must be exactly one error line naming the failed command"
