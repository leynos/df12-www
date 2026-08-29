"""What the ExecPlan's behavioural acceptance says, checked against the pages.

The ExecPlan is a completed record, so most of it is history and is left alone.
Its acceptance criteria are the exception: they state what the delivered site
does, and a reader takes them as current. One of them had drifted — it named
one script where the pages load two — and nothing caught it, because no test
had ever read the plan.

These hold the script contract against the templates that emit it. The
stylesheet half is covered by `test_weaver_build.py`, which reads the built
tree; this is about whether the plan still describes the same thing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECPLAN = REPO_ROOT / "docs" / "execplans" / "weaver-daisy-migration.md"
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"

# The two scripts every Weaver page loads, in the order it loads them.
# Telemetry first: it installs the seam the drawer reports through, and the
# drawer reports on being built.
WEAVER_SCRIPTS = (
    "/weaver/assets/js/telemetry.js",
    "/weaver/assets/js/mobile-nav.js",
)

# A `<script src="...">` in a template, which is what makes a browser fetch.
# The inline smooth-scroll block carries no `src` and so does not match.
SCRIPT_SRC = re.compile(r"""<script[^>]*\ssrc\s*=\s*["']([^"']+)["']""")


@pytest.fixture(scope="module")
def script_contract() -> str:
    """Return the acceptance bullet that states the script contract.

    Scoped to that bullet rather than the whole plan, so a script path
    mentioned in the narrative — where several are, as history — cannot
    satisfy an assertion about what the acceptance criteria promise.

    The bullet's dated addendum is excluded, and deliberately: it quotes the
    superseded wording in order to record what was corrected. Reading it as
    part of the criterion would have the plan's own account of the drift
    register as the drift.
    """
    text = EXECPLAN.read_text(encoding="utf-8")
    marker = "- The page's HTML links exactly one stylesheet,"
    assert marker in text, (
        "the ExecPlan's behavioural acceptance no longer opens its "
        f"stylesheet-and-scripts bullet with {marker!r}; if the bullet has been "
        "reworded, this fixture needs to follow it rather than be deleted"
    )
    start = text.index(marker)
    remainder = text[start + 1 :]
    end = remainder.find("\n- ")
    bullet = remainder if end == -1 else remainder[:end]
    addendum = bullet.find("**Addendum")
    return bullet if addendum == -1 else bullet[:addendum]


@pytest.mark.parametrize("script", WEAVER_SCRIPTS)
def test_the_execplan_names_every_script_a_weaver_page_loads(
    script_contract: str, script: str
) -> None:
    """Both paths, or the plan understates what the pages fetch.

    Parametrized rather than asserted together so a plan that dropped one still
    reports which one, instead of failing on a set difference the reader has to
    work out.
    """
    assert script in script_contract, (
        f"the ExecPlan's script contract does not mention {script}, which every "
        f"Weaver page loads; the bullet currently reads:\n{script_contract}"
    )


def test_the_execplan_does_not_understate_the_script_count(
    script_contract: str,
) -> None:
    """The specific way this went wrong: "exactly one script", for two."""
    assert "exactly one script" not in script_contract, (
        "the ExecPlan claims a Weaver page loads exactly one script; it loads "
        f"two: {', '.join(WEAVER_SCRIPTS)}"
    )
    assert "exactly two external scripts" in script_contract, (
        "the ExecPlan should say plainly how many scripts a page loads, so the "
        f"count and the paths cannot drift apart; it reads:\n{script_contract}"
    )
    assert "exactly one stylesheet" in script_contract, (
        "the one-stylesheet requirement has gone from the acceptance bullet; it "
        "is unchanged by the script correction and should still be stated"
    )


def test_the_contract_matches_the_templates_that_emit_it() -> None:
    """What the pages actually load, read from the two shells that carry a head.

    Without this the tests above only check that the plan agrees with a tuple
    written beside them. This is what ties the tuple to the site: a script added
    to or removed from a template fails here, and the plan is then wrong until
    someone updates both.
    """
    shells = [
        source
        for source in sorted(WEAVER_TEMPLATES.rglob("*.jinja"))
        if SCRIPT_SRC.search(source.read_text(encoding="utf-8"))
    ]
    assert shells, "no Weaver template loads a script; the contract is vacuous"

    for shell in shells:
        loaded = tuple(SCRIPT_SRC.findall(shell.read_text(encoding="utf-8")))
        assert loaded == WEAVER_SCRIPTS, (
            f"{shell.relative_to(REPO_ROOT)} loads {list(loaded)}, but the "
            f"ExecPlan's acceptance promises {list(WEAVER_SCRIPTS)} in that "
            "order; update the plan and this tuple together"
        )
