"""Published femtologging routes, assets, and runnable sample contracts."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from bs4 import BeautifulSoup

# The first test also runs the shared full-site build fixture.
pytestmark = pytest.mark.timeout(300)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
SITE = PUBLIC / "femtologging"
EXPECTED_PAGE_COUNT = 28
SAMPLES = ROOT / "templates/femtologging/samples"


def test_routes_and_local_destinations_exist(built_site: Path) -> None:
    """Every published journey and local fragment resolves after a native build."""
    assert built_site.is_dir()
    pages = sorted(SITE.rglob("index.html"))
    assert len(pages) == EXPECTED_PAGE_COUNT
    for page in pages:
        soup = BeautifulSoup(page.read_text(), "html.parser")
        assert len(soup.select("h1")) == 1, page
        assert soup.select_one(
            'link[href="/femtologging/assets/styles/femtologging.css"]'
        )
        ids = [tag["id"] for tag in soup.select("[id]")]
        assert len(ids) == len(set(ids)), page
        for tag in soup.select("[href], [src]"):
            url = urlsplit(str(tag.get("href") or tag.get("src")))
            if url.scheme or url.netloc:
                continue
            target = PUBLIC / unquote(url.path).lstrip("/") if url.path else page
            if target.is_dir():
                target /= "index.html"
            assert target.is_file(), (page, tag, target)
            if url.fragment and target.suffix == ".html":
                destination = BeautifulSoup(target.read_text(), "html.parser")
                assert destination.find(id=unquote(url.fragment)), (page, tag)


def test_code_panels_match_downloadable_programs(built_site: Path) -> None:
    """Highlighted code and downloads preserve the same complete source program."""
    assert built_site.is_dir()
    seen = set()
    for page in SITE.rglob("index.html"):
        soup = BeautifulSoup(page.read_text(), "html.parser")
        for panel in soup.select(".fl-code"):
            link = panel.select_one("a[download]")
            if link is None:
                continue
            filename = Path(str(link["href"])).name
            source = (SAMPLES / filename).read_text()
            rendered = panel.select_one(".fl-syntax code")
            assert rendered is not None, page
            assert rendered.get_text().rstrip() == source.rstrip(), (page, filename)
            assert (PUBLIC / str(link["href"]).lstrip("/")).read_text() == source
            region = panel.select_one('.fl-code__scroll[tabindex="0"][aria-label]')
            assert region is not None, page
            seen.add(filename)
    assert seen == {path.name for path in SAMPLES.glob("*.py")}


def test_forthcoming_release_and_legal_art_boundaries(built_site: Path) -> None:
    """Release copy remains prospective and shared policies exclude survey fiction."""
    assert built_site.is_dir()
    for page in SITE.rglob("index.html"):
        soup = BeautifulSoup(page.read_text(), "html.parser")
        assert "0.2.0-beta1" in soup.get_text(), page
        assert "forthcoming" in soup.get_text().lower(), page
        for figure in soup.select("figure"):
            caption = figure.find("figcaption")
            assert caption is not None, page
            assert caption.get_text(strip=True), page
    design = BeautifulSoup((SITE / "design" / "index.html").read_text(), "html.parser")
    assert "fictional scientific illustration" in design.get_text().lower()
    for slug in ("privacy-policy", "terms-of-use", "code-of-conduct"):
        soup = BeautifulSoup((SITE / slug / "index.html").read_text(), "html.parser")
        assert soup.select_one(".fl-legal")
        assert not soup.select("figure, .fl-specimens"), slug


def test_chrome_offers_df12_and_legal_pages_follow_the_shared_layout(
    built_site: Path,
) -> None:
    """Every page links back to df12; legal pages use the breadcrumb panel."""
    assert built_site.is_dir()
    for page in SITE.rglob("index.html"):
        soup = BeautifulSoup(page.read_text(), "html.parser")
        for nav in ("Primary", "Mobile primary"):
            up = soup.select_one(f'nav[aria-label="{nav}"] .fl-nav__up a[href="/"]')
            assert up is not None, (page, nav)
            assert "df12" in up.get_text(), (page, nav)
    for slug in ("privacy-policy", "terms-of-use", "code-of-conduct"):
        soup = BeautifulSoup((SITE / slug / "index.html").read_text(), "html.parser")
        crumbs = soup.select('nav.fl-crumbs[aria-label="Breadcrumb"] li')
        assert crumbs[-1].get("aria-current") == "page", slug
        panel = soup.select_one(".fl-legal-page__panel")
        assert panel is not None, slug
        assert panel.select_one(".fl-legal-page__eyebrow"), slug
        assert panel.select_one("h1"), slug
        assert panel.select_one("article.fl-legal"), slug
        assert not soup.select(".fl-page-head"), slug
