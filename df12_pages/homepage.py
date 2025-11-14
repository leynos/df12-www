"""df12 homepage rendering pipeline.

This module encapsulates the logic for turning the structured homepage entry in
``config/pages.yaml`` into the static ``public/index.html`` artefact. It wires
the configuration model, Jinja environment, and filesystem writes required to
render the marketing splash page. The main entry point is ``HomePageBuilder``,
which loads the shared template macros, injects the homepage data model, and
persists the generated HTML.

Typical usage mirrors the build pipeline:

>>> from df12_pages.config import load_homepage
>>> builder = HomePageBuilder(load_homepage())
>>> output_path = builder.run()
>>> print(output_path)

The builder expects templates to reside under ``df12_pages/templates`` unless a
custom directory is provided. It relies on Jinja2 with autoescape enabled and
produces UTF-8 encoded files. Side effects include reading template files and
writing the rendered HTML to disk.
"""

from __future__ import annotations

import datetime as dt
import typing as typ
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

if typ.TYPE_CHECKING:
    from .config import HomepageConfig


class HomePageBuilder:
    """Render the marketing homepage from structured config data."""

    def __init__(
        self, homepage: HomepageConfig, *, templates_dir: Path | None = None
    ) -> None:
        """Initialize the builder and Jinja environment.

        Parameters
        ----------
        homepage : HomepageConfig
            Parsed homepage block from ``config/pages.yaml``; provides navigation
            links, hero content, systems/worlds cards, and footer metadata.
        templates_dir : Path, optional
            Directory containing Jinja templates. Defaults to
            ``df12_pages/templates`` when not supplied, ensuring the build uses
            the checked-in macros and partials.

        Notes
        -----
        Instantiating the builder resolves the template directory, configures a
        Jinja2 ``Environment`` (autoescape, trimmed blocks), and eagerly loads
        the ``home_page.jinja`` template so later ``run`` calls only handle
        rendering and filesystem writes.
        """
        self.homepage = homepage
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("home_page.jinja")

    def run(self) -> Path:
        """Render and write the homepage HTML, returning the output path.

        Returns
        -------
        Path
            Filesystem path to the rendered homepage HTML file.

        Notes
        -----
        This method creates parent directories as needed, renders the Jinja
        template with the homepage context, ensures the output ends with a
        newline, writes UTF-8 text to ``homepage.output``, and bubbles up any
        filesystem errors that arise during writing.
        """
        output_path = self.homepage.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        context = {
            "homepage": self.homepage,
            "generated_at": dt.datetime.now(dt.UTC),
        }
        html = self.template.render(**context)
        if not html.endswith("\n"):
            html += "\n"
        output_path.write_text(html, encoding="utf-8")
        return output_path
