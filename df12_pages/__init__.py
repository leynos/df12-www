"""Utilities for generating df12 marketing and docs pages.

This package exposes the CLI entry points used by `uv run pages` and Bun
scripts to render the homepage, docs index, and release-driven bundles.

Exports
-------
- ``app``: Typer application entry for subcommands.
- ``main``: Convenience function that invokes the Typer app.

Examples
--------
>>> from df12_pages import main
>>> main(["generate"])  # doctest: +SKIP
0
>>> from df12_pages import app
>>> isinstance(app.info.name, str)
True
"""

from __future__ import annotations

from .cli import app, main

__all__ = ["app", "main"]
