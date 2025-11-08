#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "cyclopts>=2.9",
#   "Jinja2>=3.1",
#   "Markdown>=3.5",
#   "PyYAML>=6.0",
#   "Pygments>=2.17",
#   "requests>=2.32",
# ]
# ///

"""CLI entrypoint for Netsuke documentation generation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import cyclopts
from cyclopts import App, Parameter

from netsuke_docs import NetsukeDocGenerator

DEFAULT_SOURCE = "https://raw.githubusercontent.com/leynos/netsuke/refs/heads/main/docs/users-guide.md"
DEFAULT_CONFIG_PATH = Path("docs/netsuke-section-layouts.yaml")

app = App(config=cyclopts.config.Env("INPUT_", command=False))


def _format_path(path: Path) -> str:
    """Return a project-relative representation of *path* when possible."""

    if path.is_absolute():
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)
    return str(path)


@app.default
def main(
    *,
    source_url: Annotated[str, Parameter()] = DEFAULT_SOURCE,
    config: Annotated[Path, Parameter()] = DEFAULT_CONFIG_PATH,
    output_dir: Annotated[Path | None, Parameter()] = None,
) -> None:
    """Render Netsuke docs using the configured layout metadata."""

    generator = NetsukeDocGenerator(source_url, layout_config_path=config)
    written = generator.run(output_dir=output_dir)
    for path in written:
        print(f"wrote {_format_path(path)}")


if __name__ == "__main__":
    app()
