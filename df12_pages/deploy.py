"""Helper routines for wrapping OpenTofu commands with managed credentials.

This module powers the ``pages init|plan|apply`` sub-commands by:

* Loading / persisting secrets in ``~/.config/df12-www/config.toml``.
* Building the environment expected by the Scaleway S3 backend, providers,
  and deploy modules (AWS_* for the backend, SCW_* + TF_VAR_* for providers).
* Bootstrapping the remote backend bucket on Scaleway Object Storage before
  invoking ``tofu init``.
* Providing thin wrappers around ``tofu plan`` and ``tofu apply`` so the CLI
  can reuse the same credential handling and backend preparation.
"""

from __future__ import annotations

import dataclasses as dc
import os
import shutil
import subprocess
import tomllib
import typing as typ
from pathlib import Path

import hcl2

DEFAULT_CONFIG_PATH = Path(
    os.getenv(
        "DF12_CONFIG_FILE",
        Path.home() / ".config" / "df12-www" / "config.toml",
    )
)
DEFAULT_VAR_FILE = Path("terraform.tfvars.prod")
DEFAULT_BACKEND_FILE = Path("backend.scaleway.tfbackend")


class CredentialError(RuntimeError):
    """Raised when required credentials are missing."""


@dc.dataclass(slots=True)
class CredentialSet:
    """Resolved credentials for backend and provider authentication."""

    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    scw_access_key: str | None = None
    scw_secret_key: str | None = None
    cloudflare_api_token: str | None = None
    github_token: str | None = None
    region: str | None = None
    s3_endpoint: str | None = None

    def with_fallbacks(self) -> "CredentialSet":
        """Return a copy where AWS/Scaleway keys fall back to one another."""
        access = self.aws_access_key_id or self.scw_access_key
        secret = self.aws_secret_access_key or self.scw_secret_key
        return CredentialSet(
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            scw_access_key=self.scw_access_key or access,
            scw_secret_key=self.scw_secret_key or secret,
            cloudflare_api_token=self.cloudflare_api_token,
            github_token=self.github_token,
            region=self.region,
            s3_endpoint=self.s3_endpoint,
        )


@dc.dataclass(slots=True)
class BackendConfig:
    """Minimal backend configuration parsed from a ``.tfbackend`` file."""

    bucket: str
    region: str
    endpoint: str | None = None

    @classmethod
    def from_file(cls, path: Path) -> "BackendConfig":
        with path.open("r", encoding="utf-8") as handle:
            data = hcl2.load(handle)
        try:
            bucket = typ.cast(str, data["bucket"])
            region = typ.cast(str, data["region"])
        except KeyError as exc:  # pragma: no cover - defensive guard
            msg = f"Missing {exc} in backend config {path}"
            raise ValueError(msg) from exc
        endpoint = None
        endpoints = typ.cast(dict[str, typ.Any], data.get("endpoints") or {})
        if "s3" in endpoints:
            endpoint = typ.cast(str, endpoints["s3"])
        return cls(bucket=bucket, region=region, endpoint=endpoint)


def _read_config(path: Path) -> CredentialSet:
    if not path.exists():
        return CredentialSet()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    auth = typ.cast(dict[str, typ.Any], data.get("auth") or {})
    return CredentialSet(
        aws_access_key_id=auth.get("aws_access_key_id"),
        aws_secret_access_key=auth.get("aws_secret_access_key"),
        scw_access_key=auth.get("scw_access_key"),
        scw_secret_key=auth.get("scw_secret_key"),
        cloudflare_api_token=auth.get("cloudflare_api_token"),
        github_token=auth.get("github_token"),
        region=auth.get("region"),
        s3_endpoint=auth.get("s3_endpoint"),
    )


def _serialize_config(creds: CredentialSet) -> str:
    lines = ["[auth]"]
    for key, value in (
        ("aws_access_key_id", creds.aws_access_key_id),
        ("aws_secret_access_key", creds.aws_secret_access_key),
        ("scw_access_key", creds.scw_access_key),
        ("scw_secret_key", creds.scw_secret_key),
        ("cloudflare_api_token", creds.cloudflare_api_token),
        ("github_token", creds.github_token),
        ("region", creds.region),
        ("s3_endpoint", creds.s3_endpoint),
    ):
        if value:
            escaped = value.replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    return "\n".join(lines) + "\n"


def save_credentials(creds: CredentialSet, path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Persist credentials to a TOML file with restrictive permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _serialize_config(creds)
    path.write_text(payload, encoding="utf-8")
    os.chmod(path, 0o600)


def resolve_credentials(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    scw_access_key: str | None = None,
    scw_secret_key: str | None = None,
    cloudflare_api_token: str | None = None,
    github_token: str | None = None,
    region: str | None = None,
    s3_endpoint: str | None = None,
    save: bool = True,
) -> CredentialSet:
    """Merge CLI, environment, and stored credentials."""
    stored = _read_config(config_path)
    resolved = CredentialSet(
        aws_access_key_id=aws_access_key_id
        or os.getenv("AWS_ACCESS_KEY_ID")
        or stored.aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key
        or os.getenv("AWS_SECRET_ACCESS_KEY")
        or stored.aws_secret_access_key,
        scw_access_key=scw_access_key
        or os.getenv("SCW_ACCESS_KEY")
        or stored.scw_access_key,
        scw_secret_key=scw_secret_key
        or os.getenv("SCW_SECRET_KEY")
        or stored.scw_secret_key,
        cloudflare_api_token=cloudflare_api_token
        or os.getenv("CLOUDFLARE_API_TOKEN")
        or os.getenv("CF_API_TOKEN")
        or stored.cloudflare_api_token,
        github_token=github_token
        or os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
        or stored.github_token,
        region=region or os.getenv("AWS_DEFAULT_REGION") or stored.region,
        s3_endpoint=s3_endpoint or os.getenv("AWS_S3_ENDPOINT") or stored.s3_endpoint,
    ).with_fallbacks()
    if not resolved.aws_access_key_id or not resolved.aws_secret_access_key:
        msg = (
            "AWS/Scaleway access key and secret key are required. "
            "Provide them via CLI options, environment, or config.toml."
        )
        raise CredentialError(msg)
    if save:
        save_credentials(resolved, path=config_path)
    return resolved


def build_env(creds: CredentialSet) -> dict[str, str]:
    """Construct an environment dict for OpenTofu and provider commands."""
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = creds.aws_access_key_id or ""
    env["AWS_SECRET_ACCESS_KEY"] = creds.aws_secret_access_key or ""
    if creds.region:
        env.setdefault("AWS_DEFAULT_REGION", creds.region)
        env.setdefault("SCW_DEFAULT_REGION", creds.region)
    if creds.s3_endpoint:
        env.setdefault("AWS_S3_ENDPOINT", creds.s3_endpoint)
    if creds.scw_access_key:
        env.setdefault("SCW_ACCESS_KEY", creds.scw_access_key)
    if creds.scw_secret_key:
        env.setdefault("SCW_SECRET_KEY", creds.scw_secret_key)
    if creds.cloudflare_api_token:
        env.setdefault("CLOUDFLARE_API_TOKEN", creds.cloudflare_api_token)
        env.setdefault("TF_VAR_cloudflare_api_token", creds.cloudflare_api_token)
    if creds.github_token:
        env.setdefault("GITHUB_TOKEN", creds.github_token)
        env.setdefault("GH_TOKEN", creds.github_token)
        env.setdefault("TF_VAR_github_token", creds.github_token)
    if creds.scw_access_key:
        env.setdefault("TF_VAR_scaleway_access_key", creds.scw_access_key)
    if creds.scw_secret_key:
        env.setdefault("TF_VAR_scaleway_secret_key", creds.scw_secret_key)
    return env


def ensure_backend_bucket(
    backend: BackendConfig, env: dict[str, str], *, aws_exe: str | None = None
) -> None:
    """Create the backend bucket if it doesn't already exist."""
    cmd = aws_exe or shutil.which("aws")
    if not cmd:
        msg = "aws CLI is required to manage the backend bucket"
        raise FileNotFoundError(msg)

    base = [cmd]
    if backend.endpoint:
        base += ["--endpoint-url", backend.endpoint]
    base += ["--region", backend.region, "s3api"]

    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            base + args,
            check=True,
            env=env,
            text=True,
            capture_output=True,
        )

    try:
        _run(["head-bucket", "--bucket", backend.bucket])
        return
    except subprocess.CalledProcessError:
        _run(
            [
                "create-bucket",
                "--bucket",
                backend.bucket,
                "--create-bucket-configuration",
                f"LocationConstraint={backend.region}",
            ]
        )


def run_tofu(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Invoke OpenTofu with the provided arguments and environment."""
    return subprocess.run(  # noqa: S603
        ["tofu"] + args,
        check=True,
        env=env,
        text=True,
    )


def init_stack(
    *,
    var_file: Path = DEFAULT_VAR_FILE,
    backend_config: Path = DEFAULT_BACKEND_FILE,
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    ensure_bucket: bool = True,
) -> None:
    """Initialize the backend and providers using managed credentials."""
    creds = credentials or resolve_credentials(config_path=config_path, save=save_credentials_flag)
    env = build_env(creds)
    backend = BackendConfig.from_file(backend_config)
    if ensure_bucket:
        ensure_backend_bucket(backend, env)
    run_tofu(
        [
            "init",
            "-backend-config",
            str(backend_config),
            "-var-file",
            str(var_file),
        ],
        env=env,
    )


def plan_stack(
    *,
    var_file: Path = DEFAULT_VAR_FILE,
    backend_config: Path = DEFAULT_BACKEND_FILE,
    plan_file: Path = Path("plan.out"),
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    run_init: bool = True,
) -> None:
    """Generate an OpenTofu plan using stored credentials."""
    creds = credentials or resolve_credentials(config_path=config_path, save=save_credentials_flag)
    env = build_env(creds)
    backend = BackendConfig.from_file(backend_config)
    ensure_backend_bucket(backend, env)
    if run_init:
        run_tofu(
            [
                "init",
                "-backend-config",
                str(backend_config),
                "-var-file",
                str(var_file),
            ],
            env=env,
        )
    run_tofu(
        [
            "plan",
            "-var-file",
            str(var_file),
            "-out",
            str(plan_file),
        ],
        env=env,
    )


def apply_stack(
    *,
    var_file: Path = DEFAULT_VAR_FILE,
    backend_config: Path = DEFAULT_BACKEND_FILE,
    plan_file: Path | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    run_init: bool = True,
) -> None:
    """Apply infrastructure changes using managed credentials."""
    creds = credentials or resolve_credentials(config_path=config_path, save=save_credentials_flag)
    env = build_env(creds)
    backend = BackendConfig.from_file(backend_config)
    ensure_backend_bucket(backend, env)
    if run_init:
        run_tofu(
            [
                "init",
                "-backend-config",
                str(backend_config),
                "-var-file",
                str(var_file),
            ],
            env=env,
        )
    if plan_file:
        args = ["apply", str(plan_file)]
    else:
        args = ["apply", "-var-file", str(var_file)]
    run_tofu(args, env=env)
