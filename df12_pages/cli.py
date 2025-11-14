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
>>> app.run(["generate", "--page", "getting-started", "--output-dir", "dist"])  # doctest: +SKIP
"""

from __future__ import annotations

import os
import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

from .bump import bump_latest_release_metadata
from .config import load_site_config
from .docs_index import DocsIndexBuilder
from .generator import PageContentGenerator
from .homepage import HomePageBuilder
from .releases import GitHubReleaseClient

DEFAULT_CONFIG = Path("config/pages.yaml")

app = App(name="pages", config=cyclopts.config.Env("INPUT_", command=False))  # type: ignore[unknown-argument]


def _format_path(path: Path) -> str:
    """Return the given path relative to cwd when possible, otherwise an absolute string."""
    if path.is_absolute():
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:  # pragma: no cover - fallback for different roots
            return str(path)
    return str(path)


@app.command(help="Generate static HTML documentation pages from Markdown.")
def generate(
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
) -> None:
    """Generate documentation pages for the requested site configuration."""
    site_config = load_site_config(config)

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
    docs_index_path = DocsIndexBuilder(site_config).run()
    print(f"wrote {_format_path(docs_index_path)}")
    if site_config.homepage:
        homepage_path = HomePageBuilder(site_config.homepage).run()
        print(f"wrote {_format_path(homepage_path)}")


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
    """Update page configs with the latest GitHub release tags."""
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


def main() -> None:
    """Invoke the Cyclopts application that powers the `pages` console command.

    Parameters
    ----------
    None

    Returns
    -------
    None
        This function executes for its side effects of parsing CLI arguments
        and running the requested subcommand.

    Examples
    --------
    >>> main()  # doctest: +SKIP
    """
    app()


if __name__ == "__main__":  # pragma: no cover - manual invocation helper
    main()
