"""Cyclopts-powered CLI for df12 page generation."""

from __future__ import annotations

import typing as typ
from pathlib import Path

import cyclopts
from cyclopts import App, Parameter

from .config import load_site_config
from .docs_index import DocsIndexBuilder
from .generator import PageContentGenerator

DEFAULT_CONFIG = Path("config/pages.yaml")

app = App(name="pages", config=cyclopts.config.Env("INPUT_", command=False))  # type: ignore[unknown-argument]


def _format_path(path: Path) -> str:
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
    page_config = site_config.get_page(page)
    generator = PageContentGenerator(
        page_config, source_url=source_url, output_dir=output_dir
    )
    written = generator.run()
    for path in written:
        print(f"wrote {_format_path(path)}")
    docs_index_path = DocsIndexBuilder(site_config).run()
    print(f"wrote {_format_path(docs_index_path)}")


def main() -> None:
    """Entrypoint used by the `pages` console script."""
    app()


if __name__ == "__main__":  # pragma: no cover - manual invocation helper
    main()
