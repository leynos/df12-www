"""Configure the MiniJinja environment shared by the site builders."""

from __future__ import annotations

import datetime as dt
import os
import typing as typ

from markupsafe import Markup, escape
from minijinja import Environment, load_from_path, pass_state

from .jinja_highlight import highlight_code

if typ.TYPE_CHECKING:
    from pathlib import Path

    from minijinja._lowlevel import State


def build_timestamp() -> dt.datetime:
    """Return the UTC build time, honouring a reproducible build epoch.

    Returns
    -------
    datetime.datetime
        The instant specified by ``SOURCE_DATE_EPOCH`` in Unix seconds,
        or the current UTC time when the variable is unset.

    Raises
    ------
    ValueError
        If ``SOURCE_DATE_EPOCH`` is set but is not a base-ten integer. A
        malformed epoch is reported rather than ignored, so a reproducible
        build cannot silently fall back to the wall clock.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is None:
        return dt.datetime.now(dt.UTC)
    return dt.datetime.fromtimestamp(int(epoch), dt.UTC)


@pass_state
def _finalize(state: State, value: object) -> object:
    """Keep URL-valued macros comparable to raw hrefs when HTML escaping."""
    if state.auto_escape == "html" and isinstance(value, str):
        return escape(value)
    return NotImplemented


def _forceescape(value: object) -> Markup:
    """Escape captured markup again for use inside an attribute."""
    return escape(str(value))


def template_environment(
    directory: Path,
    *,
    variables: dict[str, object] | None = None,
    escape_by_suffix: bool = False,
) -> Environment:
    """Load templates from directory with the builder's HTML escaping policy.

    Parameters
    ----------
    directory : Path
        Root for named templates, imports and includes.
    variables : dict[str, object], optional
        Site values made available to imported macros as well as page templates.
    escape_by_suffix : bool
        Escape only HTML and XML templates for the document and index builders.
        The other builders enable HTML escaping for their ``.jinja`` files.

    Returns
    -------
    Environment
        A MiniJinja environment that loads templates on first use.
    """
    env = Environment(
        loader=load_from_path(directory),
        auto_escape_callback=lambda name: (
            not escape_by_suffix or name.lower().endswith((".html", ".xml"))
        ),
        trim_blocks=True,
        lstrip_blocks=True,
        globals=variables,
        filters={
            "highlight": highlight_code,
            "forceescape": _forceescape,
            "index": list.index,
        },
    )
    env.finalizer = _finalize
    return env
