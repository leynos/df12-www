"""Reading a snapshot that may not be one.

A snapshot directory is written by `capture` but read back by path, so it can
be stale, truncated by an interrupted run, or from another tool entirely. Each
of those has to name the file rather than surface as a traceback from inside
the normalization.
"""

from __future__ import annotations

import json
import typing as typ

import pytest

from tests.support.weaver_harness import load

if typ.TYPE_CHECKING:
    from pathlib import Path

normalize = load("weaver_snapshot_normalize")
document = load("weaver_snapshot_document")


def test_a_parsed_snapshot_renders_without_touching_the_filesystem() -> None:
    """The rendering is pure, so it can be checked on a literal payload."""
    payload = {
        "meta": {"url": "http://127.0.0.1:8099/weaver/", "browser": "chromium"},
        "payload": {
            "tree": {
                "tag": "html",
                "styleDiff": {"--tw-ring-color": "rgb(1, 2, 3)", "color": "#ffffff"},
                "children": [],
            }
        },
    }
    rendered = document._rendered_tree(payload)

    assert "--tw-ring-color" not in rendered, (
        f"the Tailwind internal survived into {rendered!r}"
    )
    assert "chromium" not in rendered, (
        "the capture envelope records when a snapshot was taken, not what the "
        f"page looks like, so it must not reach the diff; got {rendered!r}"
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("{ not json", "not valid JSON", id="truncated"),
        pytest.param('{"payload": {}}', "payload.tree", id="wrong-shape"),
        pytest.param('{"payload": null}', "payload.tree", id="null-payload"),
        pytest.param("[]", "payload.tree", id="not-a-mapping"),
    ],
)
def test_an_unusable_snapshot_names_the_file_it_came_from(
    tmp_path: Path, content: str, expected: str
) -> None:
    """A traceback partway through a diff hides the one thing needed: which file."""
    snapshot = tmp_path / "install.json"
    snapshot.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        document._normalized_tree(snapshot)

    message = str(caught.value.code)
    assert str(snapshot) in message, (
        f"the message should name the file; got {message!r}"
    )
    assert expected in message, f"expected {expected!r} in {message!r}"


def test_a_missing_snapshot_exits_rather_than_raising_oserror(tmp_path: Path) -> None:
    """`diff` guards the candidate but reads the baseline by glob, not by check."""
    absent = tmp_path / "gone.json"

    with pytest.raises(SystemExit) as caught:
        document._normalized_tree(absent)

    assert str(absent) in str(caught.value.code), (
        f"the message should name the file; got {caught.value.code!r}"
    )


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        pytest.param(
            {"tag": "html", "children": ["oops"]},
            "payload.tree.children[0]",
            id="child-is-a-string",
        ),
        pytest.param([1, 2], "payload.tree", id="tree-is-a-list"),
        pytest.param("nope", "payload.tree", id="tree-is-a-string"),
        pytest.param(
            {"tag": "html", "styleDiff": [1], "children": []},
            "styleDiff",
            id="style-diff-is-a-list",
        ),
        pytest.param(
            {"tag": "html", "children": "abc"},
            "children",
            id="children-is-a-string",
        ),
        pytest.param(
            {
                "tag": "html",
                "children": [{"tag": "a", "children": [{"tag": "b", "children": [7]}]}],
            },
            "children[0].children[0].children[0]",
            id="a-node-three-levels-down",
        ),
    ],
)
def test_a_snapshot_that_is_not_the_expected_shape_says_where(
    tmp_path: Path,
    shape: dict[str, object] | list[object] | str,
    expected: str,
) -> None:
    """The normalization reaches for `.get` on every node, so a scalar is fatal.

    Before the shape was checked, each of these surfaced from deep inside the
    recursion as `'str' object has no attribute 'get'` — an `AttributeError`,
    which the read boundary did not catch, naming neither the file nor the
    node. A snapshot from an interrupted capture or a different tool looks
    exactly like this.
    """
    snapshot = tmp_path / "install.json"
    snapshot.write_text(json.dumps({"payload": {"tree": shape}}), encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        document._normalized_tree(snapshot)

    message = str(caught.value.code)
    assert str(snapshot) in message, (
        f"the message should name the file; got {message!r}"
    )
    assert expected in message, (
        f"the message should point at {expected!r}; got {message!r}"
    )


def test_a_well_formed_snapshot_is_still_accepted(tmp_path: Path) -> None:
    """A shape check that rejected valid input would be worse than none."""
    snapshot = tmp_path / "install.json"
    snapshot.write_text(
        json.dumps(
            {
                "payload": {
                    "tree": {
                        "tag": "html",
                        "styleDiff": {"color": "rgb(1, 2, 3)"},
                        "children": [{"tag": "body", "children": []}, {"tag": "div"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rendered = document._normalized_tree(snapshot)

    assert "rgba(1, 2, 3, 1.000)" in rendered, (
        f"the tree should have normalized rather than been rejected; got {rendered!r}"
    )


def test_a_malformed_snapshot_says_where_and_what_in_attributes() -> None:
    """A caller can read the node, the expectation, and the finding without parsing."""
    with pytest.raises(document.MalformedSnapshotError) as caught:
        document._check_node(
            {"tag": "html", "children": [{"styleDiff": 3}]}, "payload.tree"
        )
    error = caught.value
    assert error.where == "payload.tree.children[0].styleDiff", (
        "the breadcrumb names the node"
    )
    assert error.expected == "a mapping or absent", "what the harness assumed"
    assert error.actual == "int", "what it found instead"
    assert isinstance(error, document.SnapshotError), "it is a snapshot error first"
    assert (
        str(error)
        == "payload.tree.children[0].styleDiff is int, not a mapping or absent"
    )
