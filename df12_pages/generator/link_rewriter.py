"""Helpers for rewriting relative markdown links to GitHub URLs."""

from __future__ import annotations

import posixpath
import typing as typ
from urllib.parse import urlsplit

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

if typ.TYPE_CHECKING:
    from xml.etree.ElementTree import Element

    from markdown import Markdown

    from df12_pages.config import PageConfig
else:  # pragma: no cover - type-checking fallback
    Markdown = typ.Any
    Element = typ.Any
    PageConfig = typ.Any


def _build_link_rewriter(page: PageConfig) -> Extension | None:
    """Return a RelativeLinkExtension configured for the provided page."""
    if not page.repo:
        return None
    ref = page.latest_release or page.branch
    base_dir = posixpath.dirname(page.doc_path)
    return RelativeLinkExtension(page.repo, ref, base_dir)


class RelativeLinkExtension(Extension):
    """Rewrite relative markdown links to immutable GitHub URLs.

    Insert this extension into a ``markdown.Markdown`` instance to ensure that
    intra-repository links (``./foo.md``, ``../images/diagram.png``) are
    converted into absolute ``https://github.com/<repo>/blob/<ref>/...`` URLs.
    This keeps generated HTML navigable when viewed outside the cloned repo or
    when browsing release artifacts.
    """

    def __init__(self, repo: str, ref: str, base_dir: str) -> None:
        self.repo = repo
        self.ref = ref
        self.base_dir = base_dir

    def extendMarkdown(self, md: Markdown) -> None:  # type: ignore[override]  # noqa: N802
        """Register the relative-link treeprocessor on the Markdown instance."""
        processor = RelativeLinkTreeprocessor(md, self.repo, self.ref, self.base_dir)
        md.treeprocessors.register(processor, "df12_relative_links", 15)


class RelativeLinkTreeprocessor(Treeprocessor):
    """Rewrite relative markdown links to point at GitHub raw blobs."""

    def __init__(self, md: Markdown, repo: str, ref: str, base_dir: str) -> None:
        super().__init__(md)
        self.repo = repo
        self.ref = ref
        self.base_dir = base_dir

    def run(self, root: Element) -> Element:  # pragma: no cover - Markdown API
        """Rewrite relative anchors in the parsed markdown tree to GitHub URLs."""
        for element in root.iter():
            if element.tag == "a":
                href = element.get("href")
                rewritten = self._rewrite(href)
                if rewritten:
                    element.set("href", rewritten)
        return root

    def _rewrite(self, target: str | None) -> str | None:
        """Rewrite a relative link target into a GitHub raw URL when applicable."""
        if not target:
            return None

        lower = target.lower()
        invalid = lower.startswith(
            ("http://", "https://", "mailto:", "tel:", "data:", "javascript:")
        )
        if target.startswith(("#", "//")) or "://" in target:
            invalid = True

        parsed = None
        if not invalid:
            parsed = urlsplit(target)
            invalid = bool(
                parsed.scheme
                or parsed.netloc
                or (not parsed.path and parsed.fragment)
                or parsed.path.startswith("/")
            )

        joined = None
        if not invalid and parsed is not None:
            joined = posixpath.normpath(posixpath.join(self.base_dir, parsed.path))
            while joined.startswith("../"):
                joined = joined[3:]
            if joined in (".", ""):
                invalid = True

        if invalid or parsed is None or joined is None:
            return None

        url = f"https://github.com/{self.repo}/blob/{self.ref}/{joined}"
        if parsed.query:
            url = f"{url}?{parsed.query}"
        if parsed.fragment:
            url = f"{url}#{parsed.fragment}"
        return url


__all__ = [
    "RelativeLinkExtension",
    "RelativeLinkTreeprocessor",
    "_build_link_rewriter",
]
