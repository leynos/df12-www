"""Deploy pipeline: credential management, backend bootstrap, OpenTofu orchestration.

This package powers the ``pages init|plan|apply`` sub-commands.
It is split into two submodules:

* :mod:`._credentials` — loading, resolving, and persisting credentials.
* :mod:`._backend` — backend config, HCL rendering, and temporary file helpers.

``ensure_backend_bucket``, ``run_tofu``, and the ``*_stack`` orchestration
functions live in this module so that test monkeypatching via
``monkeypatch.setattr(deploy, ...)`` affects all callers without needing to
patch submodule references.

The ``subprocess`` standard-library module is also exposed at package level so
that tests can patch ``deploy.subprocess.run`` directly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import typing as typ
from pathlib import Path

from ._backend import (
    BackendConfig,
    DeployConfig,
    _format_hcl_value,
    _is_hcl_bool,
    _is_hcl_null,
    _is_hcl_number,
    _load_config,
    _materialize_backend_file,
    _materialize_tfvars,
    _resolve_backend,
)
from ._credentials import (
    _TEMP_FILE_MODE,
    DEFAULT_CONFIG_PATH,
    CredentialError,
    CredentialSet,
    build_env,
    resolve_credentials,
    save_credentials,
)


def ensure_backend_bucket(
    backend: BackendConfig, env: dict[str, str], *, aws_exe: str | None = None
) -> None:
    """Create the backend bucket if it doesn't already exist.

    Parameters
    ----------
    backend : BackendConfig
        Backend configuration identifying the bucket and region.
    env : dict[str, str]
        Environment variables passed to the ``aws`` CLI subprocess.
    aws_exe : str or None, optional
        Explicit path to the ``aws`` CLI binary.  When ``None``, the binary
        is located via :func:`shutil.which`.

    Raises
    ------
    FileNotFoundError
        If the ``aws`` CLI binary cannot be found.
    subprocess.CalledProcessError
        If the ``head-bucket`` check fails for a reason other than a missing
        bucket (i.e. the stderr does not contain ``nosuchbucket``,
        ``not found``, or ``404``).
    """
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
        return  # noqa: TRY300 -- early return is clearer than else-after-try here
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").lower()
        # Treat empty stderr as a missing-bucket signal; only re-raise when
        # stderr clearly indicates a different error (permission denied, etc.).
        bucket_present = stderr and not (
            "nosuchbucket" in stderr or "not found" in stderr or "404" in stderr
        )
        if bucket_present:
            raise
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
    """Invoke OpenTofu with the provided arguments and environment.

    Parameters
    ----------
    args : list[str]
        Command-line arguments appended after the ``tofu`` binary name.
    env : dict[str, str]
        Full environment mapping passed to the subprocess.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The completed process result.

    Raises
    ------
    FileNotFoundError
        If the ``tofu`` binary cannot be found on ``PATH``.
    subprocess.CalledProcessError
        If ``tofu`` exits with a non-zero return code.
    """
    tofu = shutil.which("tofu")
    if not tofu:
        msg = "tofu binary not found on PATH"
        raise FileNotFoundError(msg)
    return subprocess.run(  # noqa: S603
        [tofu, *args],
        check=True,
        env=env,
        text=True,
    )


def _state_has_resources(state: dict[str, typ.Any]) -> bool:
    """Whether a parsed state document records any managed resources."""
    if state.get("resources"):
        return True
    modules = state.get("modules") or []
    return any(module.get("resources") for module in modules)


def _load_json_dict(path: Path) -> dict[str, typ.Any] | None:
    """Parse *path* as JSON, returning the document or ``None`` if not a dict."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _local_state_blocks_discard(root: Path) -> bool:
    """Whether a root ``terraform.tfstate`` prevents discarding the cache."""
    local_state = root / "terraform.tfstate"
    if not local_state.exists():
        return False
    state = _load_json_dict(local_state)
    return state is None or _state_has_resources(state)


def _cached_backend_is_discardable(workdir: Path | None = None) -> bool:
    """Whether the cached backend record is a stale local backend safe to drop.

    Return ``True`` only when ``.terraform/terraform.tfstate`` records a
    ``local`` backend with the default state path and no resources, and no
    root ``terraform.tfstate`` with resources exists.  Any other drift —
    including an unreadable cache — keeps tofu's backend-change safety
    check in place so that real backend moves still demand an explicit
    migration decision.
    """
    root = workdir or Path.cwd()
    cache_path = root / ".terraform" / "terraform.tfstate"
    if not cache_path.exists():
        return False
    cached = _load_json_dict(cache_path)
    if cached is None:
        return False
    backend = cached.get("backend") or {}
    if backend.get("type") != "local" or (backend.get("config") or {}).get("path"):
        return False
    if _state_has_resources(cached):
        return False
    return not _local_state_blocks_discard(root)


def _run_tofu_init(
    materialized_backend: Path, materialized_tfvars: Path, env: dict[str, str]
) -> None:
    """Run ``tofu init``, discarding a provably stale local backend record."""
    args = ["init"]
    # The backend config is rendered fresh from the TOML config on every
    # run, so a cached local-backend record holding no state can be
    # discarded via -reconfigure; any other drift keeps tofu's
    # backend-change check so that real backend moves still demand an
    # explicit migration decision.
    if _cached_backend_is_discardable():
        args.append("-reconfigure")
    args += [
        "-backend-config",
        str(materialized_backend),
        "-var-file",
        str(materialized_tfvars),
    ]
    run_tofu(args, env=env)


def init_stack(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    ensure_bucket: bool = True,
) -> None:
    """Initialize the OpenTofu backend and providers using managed credentials.

    Parameters
    ----------
    config_path : Path, optional
        Path to the TOML config file used to load backend and site config.
    credentials : CredentialSet or None, optional
        Pre-resolved credentials; when ``None`` they are loaded and merged
        from CLI, environment, and the config file.
    save_credentials_flag : bool, optional
        Persist resolved credentials back to *config_path* when ``True``.
    ensure_bucket : bool, optional
        Call :func:`ensure_backend_bucket` before running ``tofu init`` when
        ``True``.

    Raises
    ------
    CredentialError
        If required AWS/Scaleway credentials cannot be resolved.
    FileNotFoundError
        If the ``tofu`` or ``aws`` binary is not found on ``PATH``.
    subprocess.CalledProcessError
        If any subprocess exits with a non-zero return code.
    """
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
        _run_tofu_init(materialized_backend, materialized_tfvars, env)
    finally:
        materialized_backend.unlink(missing_ok=True)
        materialized_tfvars.unlink(missing_ok=True)


def plan_stack(  # noqa: PLR0913 -- orchestration entry point needs explicit plan, config, creds, and flags
    *,
    plan_file: Path = Path("plan.out"),
    config_path: Path = DEFAULT_CONFIG_PATH,
    credentials: CredentialSet | None = None,
    save_credentials_flag: bool = True,
    run_init: bool = True,
    destroy: bool = False,
) -> None:
    """Generate an OpenTofu plan using managed credentials.

    Parameters
    ----------
    plan_file : Path, optional
        Output path for the binary plan file written by ``tofu plan -out``.
    config_path : Path, optional
        Path to the TOML config file used to load backend and site config.
    credentials : CredentialSet or None, optional
        Pre-resolved credentials; when ``None`` they are loaded and merged
        from CLI, environment, and the config file.
    save_credentials_flag : bool, optional
        Persist resolved credentials back to *config_path* when ``True``.
    run_init : bool, optional
        Run ``tofu init -reconfigure`` before planning when ``True``.
    destroy : bool, optional
        Pass ``-destroy`` to ``tofu plan`` when ``True``.

    Raises
    ------
    CredentialError
        If required AWS/Scaleway credentials cannot be resolved.
    FileNotFoundError
        If the ``tofu`` or ``aws`` binary is not found on ``PATH``.
    subprocess.CalledProcessError
        If any subprocess exits with a non-zero return code.
    """
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
            _run_tofu_init(materialized_backend, materialized_tfvars, env)
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
    """Apply infrastructure changes using managed credentials.

    Parameters
    ----------
    plan_file : Path or None, optional
        Pre-computed plan file to apply.  When ``None``, ``tofu apply`` is
        invoked with a ``-var-file`` argument instead.
    config_path : Path, optional
        Path to the TOML config file used to load backend and site config.
    credentials : CredentialSet or None, optional
        Pre-resolved credentials; when ``None`` they are loaded and merged
        from CLI, environment, and the config file.
    save_credentials_flag : bool, optional
        Persist resolved credentials back to *config_path* when ``True``.
    run_init : bool, optional
        Run ``tofu init -reconfigure`` before applying when ``True``.

    Raises
    ------
    CredentialError
        If required AWS/Scaleway credentials cannot be resolved.
    FileNotFoundError
        If the ``tofu`` or ``aws`` binary is not found on ``PATH``.
    subprocess.CalledProcessError
        If any subprocess exits with a non-zero return code.
    """
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
            _run_tofu_init(materialized_backend, materialized_tfvars, env)
        if plan_file:
            args = ["apply", str(plan_file)]
        else:
            args = ["apply", "-var-file", str(materialized_tfvars)]
        run_tofu(args, env=env)
    finally:
        materialized_backend.unlink(missing_ok=True)
        materialized_tfvars.unlink(missing_ok=True)


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "_TEMP_FILE_MODE",
    "BackendConfig",
    "CredentialError",
    "CredentialSet",
    "DeployConfig",
    "_format_hcl_value",
    "_is_hcl_bool",
    "_is_hcl_null",
    "_is_hcl_number",
    "_load_config",
    "_materialize_backend_file",
    "_materialize_tfvars",
    "_resolve_backend",
    "apply_stack",
    "build_env",
    "ensure_backend_bucket",
    "init_stack",
    "plan_stack",
    "resolve_credentials",
    "run_tofu",
    "save_credentials",
    "subprocess",
]
