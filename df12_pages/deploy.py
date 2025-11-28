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
import tempfile
import tomlkit
import typing as typ
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(
    os.getenv(
        "DF12_CONFIG_FILE",
        Path.home() / ".config" / "df12-www" / "config.toml",
    )
)

# Temporary files should be created with restrictive permissions
_TEMP_FILE_MODE = 0o600


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
    """Backend configuration persisted under the ``[backend]`` table."""

    bucket: str
    region: str
    endpoint: str | None = None
    encrypt: bool | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, typ.Any], *, path: Path | None = None) -> "BackendConfig":
        try:
            bucket = typ.cast(str, data["bucket"])
            region = typ.cast(str, data["region"])
        except KeyError as exc:
            location = f" in {path}" if path else ""
            msg = f"Missing {exc} in backend config{location}"
            raise ValueError(msg) from exc
        endpoint = typ.cast(str | None, data.get("endpoint"))
        encrypt = typ.cast(bool | None, data.get("encrypt"))
        return cls(bucket=bucket, region=region, endpoint=endpoint, encrypt=encrypt)


@dc.dataclass(slots=True)
class DeployConfig:
    """Aggregate configuration loaded from ``config.toml``."""

    auth: CredentialSet
    backend: BackendConfig
    site: dict[str, typ.Any]


def _load_config(path: Path = DEFAULT_CONFIG_PATH) -> DeployConfig:
    if not path.exists():  # pragma: no cover - defensive guard
        msg = f"Config file not found: {path}"
        raise FileNotFoundError(msg)
    data = tomlkit.parse(path.read_text(encoding="utf-8"))

    def _as_dict(table: typ.Any) -> dict[str, typ.Any]:
        return {k: v for k, v in table.items()} if table else {}

    auth_data = _as_dict(data.get("auth"))
    backend_data = _as_dict(data.get("backend"))
    site_data = _as_dict(data.get("site"))
    auth = CredentialSet(
        aws_access_key_id=auth_data.get("aws_access_key_id"),
        aws_secret_access_key=auth_data.get("aws_secret_access_key"),
        scw_access_key=auth_data.get("scw_access_key"),
        scw_secret_key=auth_data.get("scw_secret_key"),
        cloudflare_api_token=auth_data.get("cloudflare_api_token"),
        github_token=auth_data.get("github_token"),
        region=auth_data.get("region"),
        s3_endpoint=auth_data.get("s3_endpoint"),
    )
    backend = BackendConfig.from_mapping(backend_data, path=path)
    return DeployConfig(auth=auth, backend=backend, site=site_data)


def _resolve_backend(backend: BackendConfig, creds: CredentialSet) -> BackendConfig:
    """Fill backend endpoint defaults using resolved credentials."""

    endpoint = backend.endpoint or creds.s3_endpoint
    return BackendConfig(
        bucket=backend.bucket,
        region=backend.region,
        endpoint=endpoint,
        encrypt=backend.encrypt,
    )


def save_credentials(
    creds: CredentialSet,
    *,
    path: Path = DEFAULT_CONFIG_PATH,
    existing: DeployConfig | None = None,
) -> None:
    """Persist credentials back into ``config.toml`` preserving formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        doc = tomlkit.document()
    except tomlkit.exceptions.ParseError as exc:  # pragma: no cover - defensive guard
        msg = f"Unable to parse config TOML at {path}"
        raise ValueError(msg) from exc

    auth_table = doc.get("auth")
    if not isinstance(auth_table, tomlkit.items.Table):
        auth_table = tomlkit.table()

    def _set(key: str, value: str | None) -> None:
        if value is None:
            auth_table.pop(key, None)
        else:
            auth_table[key] = value

    _set("aws_access_key_id", creds.aws_access_key_id)
    _set("aws_secret_access_key", creds.aws_secret_access_key)
    _set("scw_access_key", creds.scw_access_key)
    _set("scw_secret_key", creds.scw_secret_key)
    _set("cloudflare_api_token", creds.cloudflare_api_token)
    _set("github_token", creds.github_token)
    _set("region", creds.region)
    _set("s3_endpoint", creds.s3_endpoint)

    doc["auth"] = auth_table

    if "backend" not in doc and existing:
        backend_table = tomlkit.table()
        backend_table.update(
            {
                "bucket": existing.backend.bucket,
                "region": existing.backend.region,
            }
        )
        if existing.backend.endpoint:
            backend_table["endpoint"] = existing.backend.endpoint
        if existing.backend.encrypt is not None:
            backend_table["encrypt"] = existing.backend.encrypt
        doc["backend"] = backend_table

    if "site" not in doc and existing:
        site_table = tomlkit.table()
        site_table.update(existing.site)
        doc["site"] = site_table

    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    os.chmod(path, _TEMP_FILE_MODE)


def resolve_credentials(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    config: DeployConfig | None = None,
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
    """Merge CLI, environment, stored credentials, and config.toml content."""

    deploy_config = config or _load_config(config_path)
    stored = deploy_config.auth

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
        region=region
        or os.getenv("AWS_DEFAULT_REGION")
        or stored.region
        or deploy_config.backend.region,
        s3_endpoint=s3_endpoint
        or os.getenv("AWS_S3_ENDPOINT")
        or stored.s3_endpoint
        or deploy_config.backend.endpoint,
    ).with_fallbacks()
    if not resolved.aws_access_key_id or not resolved.aws_secret_access_key:
        msg = (
            "AWS/Scaleway access key and secret key are required. "
            "Provide them via CLI options, environment, or config.toml."
        )
        raise CredentialError(msg)
    if save:
        save_credentials(resolved, path=config_path, existing=deploy_config)
    return resolved


def build_env(
    creds: CredentialSet, *, backend_region: str | None = None, backend_endpoint: str | None = None
) -> dict[str, str]:
    """Construct an environment dict for OpenTofu and provider commands."""
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = creds.aws_access_key_id or ""
    env["AWS_SECRET_ACCESS_KEY"] = creds.aws_secret_access_key or ""
    region = creds.region or backend_region
    if region:
        env.setdefault("AWS_DEFAULT_REGION", region)
        env.setdefault("SCW_DEFAULT_REGION", region)
    endpoint = creds.s3_endpoint or backend_endpoint
    if endpoint:
        env.setdefault("AWS_S3_ENDPOINT", endpoint)
        env.setdefault("AWS_ENDPOINT_URL_S3", endpoint)
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


def _materialize_backend_file(backend: BackendConfig, creds: CredentialSet) -> Path:
    """Return a temp backend file built from config.toml and resolved creds."""

    lines = [
        f'bucket = "{backend.bucket}"',
        f'region = "{backend.region}"',
    ]
    if backend.endpoint:
        lines.append('endpoints = { s3 = "' + backend.endpoint + '" }')

    has_encrypt = backend.encrypt is not None
    force_disable_encrypt = backend.endpoint and "scw.cloud" in backend.endpoint
    if force_disable_encrypt:
        lines.append("encrypt = false")
    elif has_encrypt:
        lines.append(f'encrypt = {str(backend.encrypt).lower()}')

    lines.append(f'access_key = "{creds.aws_access_key_id}"')
    lines.append(f'secret_key = "{creds.aws_secret_access_key}"')

    fd, tmp_path = tempfile.mkstemp(
        prefix="df12-backend-", suffix=".tfbackend", text=True
    )
    tmp = Path(tmp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(tmp, _TEMP_FILE_MODE)
    return tmp


def _format_hcl_value(value: typ.Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
    escaped = str(value).replace('"', '\\"')
    return f'"{escaped}"'


def _materialize_tfvars(site: dict[str, typ.Any], creds: CredentialSet) -> Path:
    """Build a temporary ``tfvars`` file from site config plus resolved creds."""

    merged: dict[str, typ.Any] = dict(site)
    merged.setdefault("cloudflare_api_token", creds.cloudflare_api_token)
    merged.setdefault("github_token", creds.github_token)
    merged.setdefault("scaleway_access_key", creds.scw_access_key)
    merged.setdefault("scaleway_secret_key", creds.scw_secret_key)
    merged.setdefault("scaleway_region", creds.region)

    lines = [f"{key} = {_format_hcl_value(value)}" for key, value in merged.items() if value is not None]

    fd, tmp_path = tempfile.mkstemp(prefix="df12-vars-", suffix=".tfvars", text=True)
    tmp = Path(tmp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(tmp, _TEMP_FILE_MODE)
    return tmp


def ensure_backend_bucket(
    backend: BackendConfig, env: dict[str, str], *, aws_exe: str | None = None
) -> None:
    """Create the backend bucket if it doesn't already exist."""
    cmd = aws_exe or shutil.which("aws")
    if not cmd:
        msg = "aws CLI is required to manage the backend bucket"
        raise FileNotFoundError(msg)

    base = [cmd]
    endpoint = backend.endpoint or env.get("AWS_S3_ENDPOINT")
    if endpoint:
        base += ["--endpoint-url", endpoint]
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
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    ensure_bucket: bool = True,
) -> None:
    """Initialize the backend and providers using managed credentials."""
    deploy_config = _load_config(config_path)
    creds = credentials or resolve_credentials(
        config_path=config_path, config=deploy_config, save=save_credentials_flag
    )
    backend = _resolve_backend(deploy_config.backend, creds)
    env = build_env(
        creds, backend_region=backend.region, backend_endpoint=backend.endpoint
    )
    materialized_backend = _materialize_backend_file(backend, creds)
    materialized_tfvars = _materialize_tfvars(deploy_config.site, creds)
    try:
        if ensure_bucket:
            ensure_backend_bucket(backend, env)
        run_tofu(
            [
                "init",
                "-backend-config",
                str(materialized_backend),
                "-var-file",
                str(materialized_tfvars),
            ],
            env=env,
        )
    finally:
        materialized_backend.unlink(missing_ok=True)
        materialized_tfvars.unlink(missing_ok=True)


def plan_stack(
    *,
    plan_file: Path = Path("plan.out"),
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    run_init: bool = True,
    destroy: bool = False,
) -> None:
    """Generate an OpenTofu plan using stored credentials."""
    deploy_config = _load_config(config_path)
    creds = credentials or resolve_credentials(
        config_path=config_path, config=deploy_config, save=save_credentials_flag
    )
    backend = _resolve_backend(deploy_config.backend, creds)
    materialized_backend = _materialize_backend_file(backend, creds)
    materialized_tfvars = _materialize_tfvars(deploy_config.site, creds)
    env = build_env(
        creds, backend_region=backend.region, backend_endpoint=backend.endpoint
    )
    try:
        ensure_backend_bucket(backend, env)
        if run_init:
            run_tofu(
                [
                    "init",
                    "-backend-config",
                    str(materialized_backend),
                    "-var-file",
                    str(materialized_tfvars),
                ],
                env=env,
            )
        plan_args = [
            "plan",
            "-destroy" if destroy else None,
            "-var-file",
            str(materialized_tfvars),
            "-out",
            str(plan_file),
        ]
        run_tofu([arg for arg in plan_args if arg is not None], env=env)
    finally:
        materialized_backend.unlink(missing_ok=True)
        materialized_tfvars.unlink(missing_ok=True)


def apply_stack(
    *,
    plan_file: Path | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    run_init: bool = True,
) -> None:
    """Apply infrastructure changes using managed credentials."""
    deploy_config = _load_config(config_path)
    creds = credentials or resolve_credentials(
        config_path=config_path, config=deploy_config, save=save_credentials_flag
    )
    backend = _resolve_backend(deploy_config.backend, creds)
    materialized_backend = _materialize_backend_file(backend, creds)
    materialized_tfvars = _materialize_tfvars(deploy_config.site, creds)
    env = build_env(
        creds, backend_region=backend.region, backend_endpoint=backend.endpoint
    )
    try:
        ensure_backend_bucket(backend, env)
        if run_init:
            run_tofu(
                [
                    "init",
                    "-backend-config",
                    str(materialized_backend),
                    "-var-file",
                    str(materialized_tfvars),
                ],
                env=env,
            )
        if plan_file:
            args = ["apply", str(plan_file)]
        else:
            args = ["apply", "-var-file", str(materialized_tfvars)]
        run_tofu(args, env=env)
    finally:
        materialized_backend.unlink(missing_ok=True)
        materialized_tfvars.unlink(missing_ok=True)
