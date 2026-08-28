"""Shared setup for the icon-generator suites.

Both the generator's boundary tests and its publication tests need a run whose
inputs are valid and empty, so the run reaches the part under test rather than
failing earlier.
"""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

    import pytest


def _minimal_inputs(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, root: Path
) -> None:
    """Point the generator at a pair of valid inputs that render an empty macro."""
    carbon_path = root / "icons.json"
    carbon_path.write_text('{"icons": {}}', encoding="utf-8")
    mapping_path = root / "weaver-icons.yaml"
    mapping_path.write_text("icons: {}", encoding="utf-8")
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)
