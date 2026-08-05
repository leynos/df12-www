"""Cyclopts CLI entrypoint for generating df12 documentation and metadata artifacts.

The ``pages`` console script defined here can render static HTML from Markdown,
rebuild the docs index and homepage, and update release metadata in
``pages.yaml`` by talking to the GitHub API. Typical usage involves running
``pages generate`` locally or in CI to regenerate docs, and ``pages bump`` to
persist the latest GitHub releases so the docs can reference the current
version tag.

Examples
--------
Generate all pages for the default configuration:

>>> from df12_pages.cli import main
>>> main()  # doctest: +SKIP

Regenerate a single page into a custom directory:

>>> from df12_pages.cli import app
>>> app.run(
...     ["generate", "--page", "getting-started", "--output-dir", "dist"]
... )  # doctest: +SKIP
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

from .about_page import AboutPageBuilder
from .bump import bump_latest_release_metadata
from .config import SharedContentPageChrome, SiteConfig, SubSiteConfig, load_site_config
from .content_page import ContentPageGenerator
from .deploy import (
    DEFAULT_CONFIG_PATH,
    CredentialError,
    apply_stack,
    init_stack,
    plan_stack,
    resolve_credentials,
)
from .docs_index import DocsIndexBuilder
from .generator import PageContentGenerator
from .homepage import HomePageBuilder
from .releases import GitHubReleaseClient
from .shared_content import SharedContentGenerator
from .subsite_homepage import SubSiteHomePageBuilder

DEFAULT_CONFIG = Path("config/pages.yaml")

app = App(name="pages", config=cyclopts.config.Env("INPUT_", command=False))  # type: ignore[unknown-argument]


def _format_path(path: Path) -> str:
    """Return a cwd-relative path when possible, otherwise the absolute path."""
    if path.is_absolute():
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:  # pragma: no cover - fallback for different roots
            return str(path)
    return str(path)


@app.command(help="Generate static HTML documentation pages from Markdown.")
def generate(  # noqa: PLR0913  FIXME: refactor into GenerateOptions dataclass
    *,
    page: typ.Annotated[
        str | None, Parameter(help="Page identifier", env_var="INPUT_PAGE")
    ] = None,
    config: typ.Annotated[
        Path, Parameter(help="Path to site config", env_var="INPUT_CONFIG")
    ] = DEFAULT_CONFIG,
    source_url: typ.Annotated[
        str | None,
        Parameter(help="Override the page source URL", env_var="INPUT_SOURCE_URL"),
    ] = None,
    output_dir: typ.Annotated[
        Path | None,
        Parameter(help="Override the output folder", env_var="INPUT_OUTPUT_DIR"),
    ] = None,
    site: typ.Annotated[
        str | None,
        Parameter(help="Generate a specific sub-site only"),
    ] = None,
    all_sites: typ.Annotated[
        bool,
        Parameter(help="Generate main site and all sub-sites"),
    ] = False,
) -> None:
    """Generate documentation pages for the requested site configuration.

    Parameters
    ----------
    page : str or None, optional
        Specific page key to render; when ``None`` (default) all pages are
        rendered.
    config : Path, optional
        Path to the ``pages.yaml`` configuration file (overridable via
        ``INPUT_CONFIG``).
    source_url : str or None, optional
        Override markdown source URL for single-page rendering (ignored when
        multiple pages are selected).
    output_dir : Path or None, optional
        Override output directory for single-page rendering (ignored when
        multiple pages are selected).
    site : str or None, optional
        Generate only the named sub-site (e.g. ``weaver``).
    all_sites : bool
        Generate the main site plus all configured sub-sites.

    Returns
    -------
    None
        Writes rendered artifacts and logs the generated paths.

    Raises
    ------
    ValueError
        If ``--site`` and ``--all-sites`` are both supplied (mutually
        exclusive).  If ``--source-url`` or ``--output-dir`` overrides are
        combined with ``--site``.  If ``--all-sites`` is combined with any
        partial-render override (``--page``, ``--source-url``,
        ``--output-dir``).  If ``source_url`` or ``output_dir`` overrides are
        supplied when more than one page is requested.  If ``--site`` names an
        unknown sub-site.
    """
    if site and all_sites:
        msg = "--site and --all-sites are mutually exclusive"
        raise ValueError(msg)
    if site and (source_url is not None or output_dir is not None):
        msg = "--source-url and --output-dir are not supported with --site"
        raise ValueError(msg)
    if all_sites and (
        page is not None or source_url is not None or output_dir is not None
    ):
        msg = (
            "--all-sites does not support partial render overrides"
            " (--page, --source-url, --output-dir)"
        )
        raise ValueError(msg)

    site_config = load_site_config(config)

    if site:
        if site not in site_config.sites:
            available = ", ".join(sorted(site_config.sites))
            msg = f"Unknown site '{site}'. Known sites: {available}"
            raise ValueError(msg)
        _generate_subsite(site_config, site_config.sites[site], page=page)
        return

    _generate_main_site(
        site_config,
        page=page,
        source_url=source_url,
        output_dir=output_dir,
    )

    if all_sites:
        for subsite in site_config.sites.values():
            _generate_subsite(site_config, subsite)


def _generate_main_site(
    site_config: SiteConfig,
    *,
    page: str | None = None,
    source_url: str | None = None,
    output_dir: Path | None = None,
) -> None:
    """Generate the main df12 site pages."""
    shared_output_root = (
        site_config.docs_index_output.parent
        if site_config.docs_index_output is not None
        else Path("public")
    )
    if page:
        target_pages = [site_config.get_page(page)]
    else:
        target_pages = list(site_config.pages.values())

    if len(target_pages) > 1 and (source_url or output_dir):
        msg = "Cannot override source_url/output_dir when generating multiple pages."
        raise ValueError(msg)

    for page_config in target_pages:
        generator = PageContentGenerator(
            page_config, source_url=source_url, output_dir=output_dir
        )
        written = generator.run()
        for path in written:
            print(f"wrote {_format_path(path)}")

    if page:
        return

    docs_index_path = DocsIndexBuilder(site_config).run()
    print(f"wrote {_format_path(docs_index_path)}")
    if site_config.homepage:
        homepage_path = HomePageBuilder(site_config.homepage).run()
        print(f"wrote {_format_path(homepage_path)}")
    if site_config.about:
        about_path = AboutPageBuilder(site_config.about).run()
        print(f"wrote {_format_path(about_path)}")

    # Shared content for main site
    for sc in site_config.shared_content.values():
        sc_path = SharedContentGenerator(sc, shared_output_root).run()
        print(f"wrote {_format_path(sc_path)}")


def _copy_static_assets(subsite: SubSiteConfig) -> None:
    """Copy ``subsite`` static assets to its output directory.

    Parameters
    ----------
    subsite : SubSiteConfig
        Sub-site configuration whose ``static_assets_dir`` will be copied.

    Raises
    ------
    ValueError
        If ``static_assets_dir`` is configured but does not exist or is not
        a directory.
    """
    if not subsite.static_assets_dir:
        return
    if not subsite.static_assets_dir.is_dir():
        msg = (
            f"Sub-site '{subsite.key}' static_assets_dir does not exist "
            f"or is not a directory: {subsite.static_assets_dir}"
        )
        raise ValueError(msg)
    dest = subsite.output_dir / "assets"
    shutil.copytree(subsite.static_assets_dir, dest, dirs_exist_ok=True)
    print(f"[{subsite.key}] copied static assets to {_format_path(dest)}")


def _generate_subsite(
    site_config: SiteConfig,
    subsite: SubSiteConfig,
    *,
    page: str | None = None,
) -> None:
    """Generate all pages for a single sub-site.

    Parameters
    ----------
    site_config : SiteConfig
        Top-level site configuration, used to resolve shared content.
    subsite : SubSiteConfig
        Configuration for the sub-site to generate.
    page : str or None, optional
        Specific page key to render; when ``None`` (default) all pages,
        the docs index, homepage, about page, shared content, content
        pages, and static assets are rendered.

    Raises
    ------
    ValueError
        If ``page`` is supplied but does not name a known page in
        ``subsite.pages``.  If a ``shared_content_refs`` entry does not
        resolve to a known shared-content block.  If
        ``static_assets_dir`` is configured but does not exist or is not
        a directory.
    """
    templates_dir = subsite.templates_dir

    # Doc pages
    if page:
        if page not in subsite.pages:
            available = ", ".join(sorted(subsite.pages))
            msg = f"Unknown page '{page}' in site '{subsite.key}'. Known: {available}"
            raise ValueError(msg)
        target_pages = [subsite.pages[page]]
    else:
        target_pages = list(subsite.pages.values())

    for page_config in target_pages:
        generator = PageContentGenerator(page_config, templates_dir=templates_dir)
        written = generator.run()
        for path in written:
            print(f"[{subsite.key}] wrote {_format_path(path)}")

    if page is not None:
        return

    # Docs index
    if subsite.pages and subsite.docs_index_output:
        scoped = SiteConfig(
            pages=subsite.pages,
            docs_index_output=subsite.docs_index_output,
            theme=subsite.theme,
        )
        idx_path = DocsIndexBuilder(scoped, templates_dir=templates_dir).run()
        print(f"[{subsite.key}] wrote {_format_path(idx_path)}")

    # Homepage
    if subsite.homepage:
        hp_path = SubSiteHomePageBuilder(
            subsite.homepage,
            templates_dir=templates_dir,
            nav_links=subsite.nav_links,
            parent_link=subsite.parent_link,
            base_path=subsite.base_path,
            template_vars=subsite.template_vars,
        ).run()
        print(f"[{subsite.key}] wrote {_format_path(hp_path)}")

    # About page
    if subsite.about:
        about_path = AboutPageBuilder(subsite.about, templates_dir=templates_dir).run()
        print(f"[{subsite.key}] wrote {_format_path(about_path)}")

    # Shared content
    for ref_key in subsite.shared_content_refs:
        sc = site_config.shared_content.get(ref_key)
        if not sc:
            msg = (
                f"Sub-site '{subsite.key}' references "
                f"unknown shared content '{ref_key}'."
            )
            raise ValueError(msg)
        sc_path = SharedContentGenerator(
            sc,
            subsite.output_dir,
            templates_dir=templates_dir,
            page_chrome=SharedContentPageChrome(
                nav_links=subsite.nav_links,
                parent_link=subsite.parent_link,
                stylesheet=subsite.stylesheet,
                site_title_suffix=subsite.theme.site_name,
                site_brand=subsite.theme.site_name,
            ),
        ).run()
        print(f"[{subsite.key}] wrote {_format_path(sc_path)}")

    # Content pages
    for cp_config in subsite.content_pages:
        cp_path = ContentPageGenerator(
            cp_config,
            subsite.output_dir,
            templates_dir=templates_dir,
            nav_links=subsite.nav_links,
            stylesheet=subsite.stylesheet,
            parent_link=subsite.parent_link,
            base_path=subsite.base_path,
            template_vars=subsite.template_vars,
        ).run()
        print(f"[{subsite.key}] wrote {_format_path(cp_path)}")

    # Static assets
    _copy_static_assets(subsite)


@app.command(help="Record the latest GitHub release tag for each configured page.")
def bump(
    *,
    config: typ.Annotated[
        Path, Parameter(help="Path to site config", env_var="INPUT_CONFIG")
    ] = DEFAULT_CONFIG,
    github_token: typ.Annotated[
        str | None,
        Parameter(
            help="Optional GitHub token (falls back to GITHUB_TOKEN)",
            env_var="INPUT_GITHUB_TOKEN",
        ),
    ] = None,
    github_api_url: typ.Annotated[
        str,
        Parameter(
            help="Override the GitHub API base URL", env_var="INPUT_GITHUB_API_URL"
        ),
    ] = GitHubReleaseClient.default_api_base,
) -> None:
    """Update page configs with the latest GitHub release tags.

    Parameters
    ----------
    config : Path, optional
        Path to the site configuration file; defaults to ``config/pages.yaml``
        and can be overridden via ``INPUT_CONFIG``.
    github_token : str or None, optional
        GitHub token for authenticated release queries. If ``None``, the
        function falls back to ``GITHUB_TOKEN`` or ``GH_TOKEN`` environment
        variables before making unauthenticated requests.
    github_api_url : str, optional
        Base URL for the GitHub API, defaulting to ``https://api.github.com``;
        override when targeting GitHub Enterprise (``INPUT_GITHUB_API_URL``).

    Returns
    -------
    None
        Releases are recorded in-place within the configuration file and a
        list of updated pages is printed to stdout.
    """
    token = github_token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    client = GitHubReleaseClient(token=token, api_base=github_api_url)
    results = bump_latest_release_metadata(config_path=config, client=client)
    for page_key, release in sorted(results.items()):
        if release:
            label = release.tag_name
            if release.published_at:
                label = f"{label} ({release.published_at})"
            print(f"{page_key}: {label}")
        else:
            print(f"{page_key}: no releases found")


@app.command(help="Initialize OpenTofu backend and providers with managed creds.")
def init(  # noqa: PLR0913  FIXME: bundle credentials into CredentialsInput dataclass
    *,
    config_path: typ.Annotated[
        Path,
        Parameter(
            help="Where to store credentials (TOML)",
            env_var="DF12_CONFIG_FILE",
        ),
    ] = DEFAULT_CONFIG_PATH,
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    scw_access_key: str | None = None,
    scw_secret_key: str | None = None,
    cloudflare_api_token: str | None = None,
    github_token: str | None = None,
    region: str | None = None,
    s3_endpoint: str | None = None,
    save: bool = True,
) -> None:
    """Initialize OpenTofu backend and bootstrap the backend bucket.

    Parameters
    ----------
    config_path : Path, optional
        TOML file used to load and persist credentials; defaults to
        ``~/.config/df12-www/config.toml`` (overridable via
        ``DF12_CONFIG_FILE``).
    aws_access_key_id : str or None, optional
        AWS/Scaleway access key (highest priority over env and stored).
    aws_secret_access_key : str or None, optional
        AWS/Scaleway secret key (highest priority over env and stored).
    scw_access_key : str or None, optional
        Scaleway-specific access key (highest priority).
    scw_secret_key : str or None, optional
        Scaleway-specific secret key (highest priority).
    cloudflare_api_token : str or None, optional
        Cloudflare API token (highest priority).
    github_token : str or None, optional
        GitHub personal access token (highest priority).
    region : str or None, optional
        AWS/Scaleway region (highest priority).
    s3_endpoint : str or None, optional
        S3-compatible endpoint URL (highest priority).
    save : bool, optional
        Persist resolved credentials back to *config_path* when ``True``.

    Raises
    ------
    CredentialError
        If neither CLI arguments nor the environment nor the stored config
        can supply an AWS access key and secret key.
    FileNotFoundError
        If the ``tofu`` or ``aws`` binary is not found on ``PATH``.
    subprocess.CalledProcessError
        If ``tofu init`` or the bucket bootstrap command exits non-zero.
    """
    creds = resolve_credentials(
        config_path=config_path,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        scw_access_key=scw_access_key,
        scw_secret_key=scw_secret_key,
        cloudflare_api_token=cloudflare_api_token,
        github_token=github_token,
        region=region,
        s3_endpoint=s3_endpoint,
        save=save,
    )
    init_stack(
        config_path=config_path,
        credentials=creds,
        save_credentials_flag=save,
        ensure_bucket=True,
    )


@app.command(help="Generate a plan using stored credentials.")
def plan(
    *,
    plan_file: typ.Annotated[
        Path, Parameter(help="Where to write the binary plan")
    ] = Path("plan.out"),
    config_path: typ.Annotated[
        Path,
        Parameter(
            help="Where to store credentials (TOML)",
            env_var="DF12_CONFIG_FILE",
        ),
    ] = DEFAULT_CONFIG_PATH,
    run_init: bool = True,
    destroy: bool = False,
) -> None:
    """Generate an OpenTofu plan using stored credentials.

    Parameters
    ----------
    plan_file : Path, optional
        Output path for the binary plan file produced by ``tofu plan -out``.
        Defaults to ``plan.out`` in the current working directory.
    config_path : Path, optional
        TOML file used to load and persist credentials; defaults to
        ``~/.config/df12-www/config.toml`` (overridable via
        ``DF12_CONFIG_FILE``).
    run_init : bool, optional
        Run ``tofu init`` before planning when ``True`` (default).
    destroy : bool, optional
        Pass ``-destroy`` to ``tofu plan`` to produce a destroy plan.

    Raises
    ------
    CredentialError
        If stored credentials are missing or incomplete.
    FileNotFoundError
        If the ``tofu`` or ``aws`` binary is not found on ``PATH``.
    subprocess.CalledProcessError
        If ``tofu plan`` or a prerequisite command exits non-zero.
    """
    plan_stack(
        plan_file=plan_file,
        config_path=config_path,
        run_init=run_init,
        destroy=destroy,
    )


@app.command(help="Apply changes using stored credentials.")
def apply(
    *,
    plan_file: typ.Annotated[
        Path | None, Parameter(help="Optional plan file to apply")
    ] = None,
    config_path: typ.Annotated[
        Path,
        Parameter(
            help="Where to store credentials (TOML)",
            env_var="DF12_CONFIG_FILE",
        ),
    ] = DEFAULT_CONFIG_PATH,
    run_init: bool = True,
) -> None:
    """Apply infrastructure changes using stored credentials.

    Parameters
    ----------
    plan_file : Path or None, optional
        Pre-computed binary plan file to apply.  When ``None``, ``tofu
        apply`` is invoked with a ``-var-file`` argument instead.
    config_path : Path, optional
        TOML file used to load and persist credentials; defaults to
        ``~/.config/df12-www/config.toml`` (overridable via
        ``DF12_CONFIG_FILE``).
    run_init : bool, optional
        Run ``tofu init`` before applying when ``True`` (default).

    Raises
    ------
    CredentialError
        If stored credentials are missing or incomplete.
    FileNotFoundError
        If the ``tofu`` or ``aws`` binary is not found on ``PATH``.
    subprocess.CalledProcessError
        If ``tofu apply`` or a prerequisite command exits non-zero.
    """
    apply_stack(
        plan_file=plan_file,
        config_path=config_path,
        run_init=run_init,
    )


_STDERR_DETAIL_LIMIT = 2000


def _describe_failed_command(exc: subprocess.CalledProcessError) -> str:
    """Return a short human-readable name for the command that failed."""
    match exc.cmd:
        case [exe, arg, *_]:
            return f"{Path(str(exe)).name} {arg}"
        case [exe]:
            return Path(str(exe)).name
        case cmd:
            return str(cmd)


def main() -> None:
    """Invoke the Cyclopts application that powers the `pages` console command.

    Expected operational failures (a subprocess exiting non-zero, a missing
    binary, or unresolvable credentials) are reported as a single-line error
    message rather than a traceback.  When the failed subprocess captured
    its stderr (as the backend-bucket bootstrap does), a bounded excerpt is
    relayed first so the diagnostic is not lost; otherwise the subprocess
    has already written its diagnostics to the terminal.

    Parameters
    ----------
    None

    Returns
    -------
    None
        This function executes for its side effects of parsing CLI arguments
        and running the requested subcommand.

    Raises
    ------
    SystemExit
        With the subprocess's exit status when a command fails, or ``1`` for
        missing binaries and credential errors.

    Examples
    --------
    >>> main()  # doctest: +SKIP
    """
    try:
        app()
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        if detail:
            print(detail[:_STDERR_DETAIL_LIMIT], file=sys.stderr)
        print(
            f"error: {_describe_failed_command(exc)} exited with "
            f"status {exc.returncode}",
            file=sys.stderr,
        )
        raise SystemExit(exc.returncode or 1) from None
    except (FileNotFoundError, CredentialError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    else:
        return


if __name__ == "__main__":  # pragma: no cover - manual invocation helper
    main()
