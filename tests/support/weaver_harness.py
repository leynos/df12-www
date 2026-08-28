"""Load the Weaver snapshot harness the way running it by path would.

The harness is a set of sibling modules under `scripts/`, not an installed
package, and they import each other by bare name — which works because a
script run by path has its own directory on `sys.path`. Loading one of them
from a test has to reproduce that, or the first sibling import fails with
`ModuleNotFoundError`.

Modules are cached by name, so a test module asking for one the session has
already loaded gets the same object. That matters for `monkeypatch`: patching
an attribute on a module is only visible to code holding that same module.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def load(name: str) -> ModuleType:
    """Import one harness module by name, as running the script would.

    Parameters
    ----------
    name
        The module's name without its extension, such as
        ``"weaver_snapshot_colour"``.

    Returns
    -------
    ModuleType
        The imported module.
    """
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        message = f"scripts/{name}.py could not be loaded"
        raise ImportError(message)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so a sibling importing it mid-load gets this
    # object rather than a second copy.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_snapshot(directory: Path, name: str, **style: str) -> Path:
    """Write a minimal css-view snapshot file and return its path.

    Shared by the validation and command suites, which both need a snapshot
    that parses and normalizes without a browser having produced it.

    Parameters
    ----------
    directory
        Where to write it.
    name
        The snapshot's stem, without the extension.
    style
        Computed styles for the single node the tree contains.

    Returns
    -------
    Path
        The file written.
    """
    payload = {
        "payload": {
            "tree": {
                "tag": "div",
                "classes": [],
                "styleDiff": dict(style),
                "children": [],
            }
        }
    }
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
