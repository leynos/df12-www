"""Backend configuration, HCL rendering, and bucket bootstrap for the deploy pipeline.

This module provides the ``BackendConfig`` and ``DeployConfig`` dataclasses,
helpers for writing temporary OpenTofu backend and tfvars files, and the
``ensure_backend_bucket`` function that creates the Scaleway Object Storage
bucket when it does not yet exist.
"""

from __future__ import annotations

import dataclasses as dc
import os
import tempfile
import typing as typ
from pathlib import Path

import tomlkit

from ._credentials import _TEMP_FILE_MODE, DEFAULT_CONFIG_PATH, CredentialSet


@dc.dataclass(slots=True)
class BackendConfig:
    """Backend configuration persisted under the ``[backend]`` table."""

    bucket: str
    region: str
    endpoint: str | None = None
    encrypt: bool | None = None

    @classmethod
    def from_mapping(
        cls, data: dict[str, typ.Any], *, path: Path | None = None
    ) -> BackendConfig:
        """Create a BackendConfig from a mapping dictionary.

        Parameters
        ----------
        data
            Raw key/value mapping (typically parsed from TOML).
        path
            Source file path, included in error messages when provided.

        Raises
        ------
        ValueError
            If *bucket* or *region* is missing from *data*.
        TypeError
            If *bucket*, *region*, *endpoint*, or *encrypt* has the wrong type.
        """
        try:
            bucket = data["bucket"]
            region = data["region"]
        except KeyError as exc:
            location = f" in {path}" if path else ""
            msg = f"Missing {exc} in backend config{location}"
            raise ValueError(msg) from exc
        if not isinstance(bucket, str) or not isinstance(region, str):
            msg = "bucket and region must be strings"
            raise TypeError(msg)
        endpoint = data.get("endpoint")
        encrypt = data.get("encrypt")
        if endpoint is not None and not isinstance(endpoint, str):
            msg = "endpoint must be a string"
            raise TypeError(msg)
        if encrypt is not None and not isinstance(encrypt, bool):
            msg = "encrypt must be a boolean"
            raise TypeError(msg)
        return cls(bucket=bucket, region=region, endpoint=endpoint, encrypt=encrypt)


@dc.dataclass(slots=True)
class DeployConfig:
    """Aggregate configuration loaded from ``config.toml``."""

    auth: CredentialSet
    backend: BackendConfig
    site: dict[str, typ.Any]


def _load_config(path: Path = DEFAULT_CONFIG_PATH) -> DeployConfig:
    """Load and parse the TOML config file into a :class:`DeployConfig`.

    Parameters
    ----------
    path : Path, optional
        Filesystem path of the TOML configuration file.

    Returns
    -------
    DeployConfig
        Parsed aggregate configuration.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist on the filesystem.
    ValueError
        If required keys are missing from the backend section.
    """
    if not path.exists():  # pragma: no cover - defensive guard
        msg = f"Config file not found: {path}"
        raise FileNotFoundError(msg)
    data = tomlkit.parse(path.read_text(encoding="utf-8"))

    def _as_dict(table: typ.Any) -> dict[str, typ.Any]:  # noqa: ANN401  FIXME: narrow once tomlkit exposes typed table API  https://github.com/leynos/df12-www/issues/34
        return dict(table.items()) if table else {}

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
    """Fill backend endpoint defaults using resolved credentials.

    Parameters
    ----------
    backend : BackendConfig
        Backend configuration as parsed from the TOML file.
    creds : CredentialSet
        Resolved credentials, consulted for a fallback S3 endpoint.

    Returns
    -------
    BackendConfig
        Copy of *backend* with *endpoint* populated from *creds* when absent.
    """
    endpoint = backend.endpoint or creds.s3_endpoint
    return BackendConfig(
        bucket=backend.bucket,
        region=backend.region,
        endpoint=endpoint,
        encrypt=backend.encrypt,
    )


def _materialize_backend_file(backend: BackendConfig, creds: CredentialSet) -> Path:
    """Return a temp backend file built from config.toml and resolved creds.

    Parameters
    ----------
    backend : BackendConfig
        Backend configuration including bucket, region, and optional endpoint.
    creds : CredentialSet
        Resolved credentials supplying the access and secret keys.

    Returns
    -------
    Path
        Path to the temporary ``.tfbackend`` file.  The caller is responsible
        for unlinking this file when it is no longer needed.

    Raises
    ------
    OSError
        If the temporary file cannot be created or written.
    """
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
        lines.append(f"encrypt = {str(backend.encrypt).lower()}")

    lines.append(f'access_key = "{creds.aws_access_key_id}"')
    lines.append(f'secret_key = "{creds.aws_secret_access_key}"')

    fd, tmp_path = tempfile.mkstemp(
        prefix="df12-backend-", suffix=".tfbackend", text=True
    )
    tmp = Path(tmp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    tmp.chmod(_TEMP_FILE_MODE)
    return tmp


def _is_hcl_null(value: object) -> bool:
    """Return ``True`` when *value* should be rendered as HCL ``null``."""
    return value is None


def _is_hcl_bool(value: object) -> bool:
    """Return ``True`` when *value* should be rendered as an HCL boolean.

    Notes
    -----
    ``bool`` is a subclass of ``int`` in Python, so this predicate must be
    tested *before* :func:`_is_hcl_number`.
    """
    return isinstance(value, bool)


def _is_hcl_number(value: object) -> bool:
    """Return ``True`` when *value* should be rendered as an HCL number literal.

    Notes
    -----
    Booleans are excluded because ``bool`` is a subclass of ``int``; callers
    must apply :func:`_is_hcl_bool` first.
    """
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _format_hcl_value(value: typ.Any) -> str:  # noqa: ANN401 -- HCL values are heterogeneous by nature
    """Format a Python value as an HCL literal string.

    Parameters
    ----------
    value : Any
        Python value to serialise.  Supported types are ``None`` (→
        ``null``), ``bool`` (→ ``true``/``false``), ``int``/``float`` (→
        bare numeric literal), and everything else (→ double-quoted string).

    Returns
    -------
    str
        HCL literal representation of *value*.
    """
    if _is_hcl_bool(value):
        return "true" if value else "false"
    if _is_hcl_number(value):
        return str(value)
    if _is_hcl_null(value):
        return "null"
    escaped = str(value).replace('"', '\\"')
    return f'"{escaped}"'


def _materialize_tfvars(site: dict[str, typ.Any], creds: CredentialSet) -> Path:
    """Build a temporary ``tfvars`` file from site config plus resolved creds.

    Parameters
    ----------
    site : dict[str, Any]
        Site-level variables parsed from the TOML ``[site]`` table.
    creds : CredentialSet
        Resolved credentials used to supply default provider variables.

    Returns
    -------
    Path
        Path to the temporary ``.tfvars`` file.  The caller is responsible
        for unlinking this file when it is no longer needed.

    Raises
    ------
    OSError
        If the temporary file cannot be created or written.
    """
    merged: dict[str, typ.Any] = dict(site)
    merged.setdefault("cloudflare_api_token", creds.cloudflare_api_token)
    merged.setdefault("github_token", creds.github_token)
    merged.setdefault("scaleway_access_key", creds.scw_access_key)
    merged.setdefault("scaleway_secret_key", creds.scw_secret_key)
    merged.setdefault("scaleway_region", creds.region)

    lines = [
        f"{key} = {_format_hcl_value(value)}"
        for key, value in merged.items()
        if value is not None
    ]

    fd, tmp_path = tempfile.mkstemp(prefix="df12-vars-", suffix=".tfvars", text=True)
    tmp = Path(tmp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    tmp.chmod(_TEMP_FILE_MODE)
    return tmp


__all__ = [
    "BackendConfig",
    "DeployConfig",
    "_format_hcl_value",
    "_is_hcl_bool",
    "_is_hcl_null",
    "_is_hcl_number",
    "_load_config",
    "_materialize_backend_file",
    "_materialize_tfvars",
    "_resolve_backend",
]
