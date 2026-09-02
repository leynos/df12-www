"""Transport claims in maintained Weaver documentation."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"
WEAVER_EXECPLAN = REPO_ROOT / "docs" / "execplans" / "weaver-content-refresh.md"
TCP_TRANSPORT = re.compile(r"\bTCP\b|tcp://", re.IGNORECASE)
UNQUALIFIED_NO_NETWORK_ENDPOINT = re.compile(r"\bno network endpoint\b", re.IGNORECASE)


def _maintained_weaver_prose() -> str:
    """Return the Weaver templates and content-refresh plan as one corpus."""
    sources = sorted(WEAVER_TEMPLATES.rglob("*.jinja"))
    sources.append(WEAVER_EXECPLAN)
    return "\n".join(source.read_text(encoding="utf-8") for source in sources)


def test_tcp_transport_has_no_unqualified_no_network_endpoint_claim() -> None:
    """Supported TCP wording must not coexist with an absolute network denial."""
    prose = _maintained_weaver_prose()

    documents_tcp = TCP_TRANSPORT.search(prose) is not None
    denies_any_network_endpoint = (
        UNQUALIFIED_NO_NETWORK_ENDPOINT.search(prose) is not None
    )

    assert not (documents_tcp and denies_any_network_endpoint), (
        "Weaver documents TCP transport and an unqualified 'no network endpoint' "
        "claim; qualify the endpoint as loopback-only or remotely unreachable"
    )
