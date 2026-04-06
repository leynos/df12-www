"""Credential loading, resolution, and persistence for the deploy pipeline.

This module handles reading and writing credentials from ``~/.config/df12-www/
config.toml``, merging CLI arguments with environment variables and stored values,
and constructing the environment dict required by OpenTofu and the AWS/Scaleway
provider commands.
"""

from __future__ import annotations

import dataclasses as dc
import os
import typing as typ
from pathlib import Path

import tomlkit
import tomlkit.exceptions
import tomlkit.items

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

    def with_fallbacks(self) -> CredentialSet:
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


def save_credentials(
    creds: CredentialSet,
    *,
    path: Path = DEFAULT_CONFIG_PATH,
    existing: typ.Any = None,  # noqa: ANN401  FIXME: https://github.com/leynos/df12-www/issues/34 — workaround for circular import until resolved
) -> None:
    """Persist credentials back into ``config.toml`` preserving formatting.

    Parameters
    ----------
    creds : CredentialSet
        Resolved credentials to persist.
    path : Path, optional
        Destination TOML file path; parent directories are created if absent.
    existing : DeployConfig or None, optional
        Previously loaded config used to seed ``[backend]`` and ``[site]``
        sections when they are absent from the on-disk file.

    Raises
    ------
    ValueError
        If the existing file cannot be parsed as valid TOML.
    OSError
        If the file cannot be written or ``chmod``'d.
    """
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
    path.chmod(_TEMP_FILE_MODE)


def resolve_credentials(  # noqa: PLR0913 -- each credential maps to a distinct auth backend
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    config: typ.Any = None,  # noqa: ANN401  FIXME: https://github.com/leynos/df12-www/issues/34 — workaround for circular import until resolved
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
    """Merge CLI, environment, stored credentials, and config.toml content.

    Parameters
    ----------
    config_path : Path, optional
        Path to the TOML config file used as the credential store.
    config : DeployConfig or None, optional
        Pre-loaded config; if ``None`` the file at *config_path* is parsed.
    aws_access_key_id : str or None, optional
        AWS/Scaleway access key from the CLI (highest priority).
    aws_secret_access_key : str or None, optional
        AWS/Scaleway secret key from the CLI (highest priority).
    scw_access_key : str or None, optional
        Scaleway access key from the CLI (highest priority).
    scw_secret_key : str or None, optional
        Scaleway secret key from the CLI (highest priority).
    cloudflare_api_token : str or None, optional
        Cloudflare API token from the CLI (highest priority).
    github_token : str or None, optional
        GitHub token from the CLI (highest priority).
    region : str or None, optional
        AWS/Scaleway region from the CLI (highest priority).
    s3_endpoint : str or None, optional
        S3-compatible endpoint URL from the CLI (highest priority).
    save : bool, optional
        Write resolved credentials back to *config_path* when ``True``.

    Returns
    -------
    CredentialSet
        Fully merged and validated credentials.

    Raises
    ------
    CredentialError
        If the resolved AWS access key or secret key is empty after merging
        all sources.
    """
    # Import here to avoid circular imports between _credentials and _backend
    from ._backend import _load_config  # noqa: PLC0415

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
    creds: CredentialSet,
    *,
    backend_region: str | None = None,
    backend_endpoint: str | None = None,
) -> dict[str, str]:
    """Construct an environment dict for OpenTofu and provider commands.

    Parameters
    ----------
    creds : CredentialSet
        Resolved credentials used to populate env vars.
    backend_region : str or None, optional
        Region from the backend config, used when *creds.region* is absent.
    backend_endpoint : str or None, optional
        Endpoint URL from the backend config, used when *creds.s3_endpoint*
        is absent.

    Returns
    -------
    dict[str, str]
        Copy of ``os.environ`` augmented with credential-derived variables.
    """
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


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "_TEMP_FILE_MODE",
    "CredentialError",
    "CredentialSet",
    "build_env",
    "resolve_credentials",
    "save_credentials",
]
