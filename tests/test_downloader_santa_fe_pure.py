"""P2 tests — pure functions in scrapper/downloader_santa_fe.py (no I/O, no async, no mocks)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapper.downloader_santa_fe import (
    SKIP_PREFIX,
    build_task_list,
    extract_body_text,
    extract_wp_pdf_url,
    is_pending,
)
from scrapper.santafe.sitemap import _parse_sitemap_locs, _sitemap_matches
from scrapper.santafe.tasks import (
    _collection_from_url,
    _dest_folder,
    _normativa_type,
    _slug_from_url,
)

# ── _slug_from_url ────────────────────────────────────────────────────────────


class TestSlugFromUrl:
    def test_basic_slug(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-123-2024/"
        assert _slug_from_url(url) == "decreto-dmm-123-2024"

    def test_slug_without_trailing_slash(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-0001-2023"
        assert _slug_from_url(url) == "ordenanza-0001-2023"

    def test_slug_from_non_normativa(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/compras-y-contrataciones/compra-99/"
        assert _slug_from_url(url) == "compra-99"

    def test_slug_from_root(self) -> None:
        # root path → last segment after split is ""
        url = "https://transparencia.santafeciudad.gov.ar/"
        result = _slug_from_url(url)
        assert isinstance(result, str)


# ── _collection_from_url ──────────────────────────────────────────────────────


class TestCollectionFromUrl:
    def test_normativa_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1/"
        assert _collection_from_url(url) == "normativa"

    def test_compras_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/compras-y-contrataciones/item/"
        assert _collection_from_url(url) == "compras-y-contrataciones"

    def test_convocatoria_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/convocatoria/licitacion/"
        assert _collection_from_url(url) == "convocatoria"

    def test_contratacion_obra_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/contratacion-obra/obra-abc/"
        assert _collection_from_url(url) == "contratacion-obra"


# ── _normativa_type ───────────────────────────────────────────────────────────


class TestNormativaType:
    @pytest.mark.parametrize(
        ("slug", "expected_folder"),
        [
            ("resolucion-conjunta-001-2024", "resolucion_conjunta"),
            ("resolucion-dem-005-2023", "resolucion_dem"),
            ("resolucion-hcm-010-2022", "resolucion_hcm"),
            ("decreto-dmm-200-2021", "decreto_dmm"),
            ("decreto-dpb-300-2020", "decreto_dpb"),
            ("ordenanza-0050-2019", "ordenanza"),
        ],
    )
    def test_known_prefixes(self, slug: str, expected_folder: str) -> None:
        assert _normativa_type(slug) == expected_folder

    def test_unknown_slug_returns_otros(self) -> None:
        assert _normativa_type("contrato-municipal-1-2024") == "otros"

    def test_empty_slug_returns_otros(self) -> None:
        assert _normativa_type("") == "otros"

    def test_resolucion_conjunta_wins_over_shorter_prefix(self) -> None:
        # Must match resolucion-conjunta- before resolucion-dem- or resolucion-hcm-
        slug = "resolucion-conjunta-99-2024"
        assert _normativa_type(slug) == "resolucion_conjunta"


# ── _dest_folder ──────────────────────────────────────────────────────────────


class TestDestFolder:
    def test_normativa_decreto_dmm(self) -> None:
        output = Path("/output")
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        result = _dest_folder(output, url)
        assert result == Path("/output/normativa/decreto_dmm")

    def test_normativa_ordenanza(self) -> None:
        output = Path("/output")
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2023/"
        result = _dest_folder(output, url)
        assert result == Path("/output/normativa/ordenanza")

    def test_normativa_unknown_slug_goes_to_otros(self) -> None:
        output = Path("/output")
        url = "https://transparencia.santafeciudad.gov.ar/normativa/algo-raro-1-2024/"
        result = _dest_folder(output, url)
        assert result == Path("/output/normativa/otros")

    def test_non_normativa_collection(self) -> None:
        output = Path("/output")
        url = "https://transparencia.santafeciudad.gov.ar/compras-y-contrataciones/compra-5/"
        result = _dest_folder(output, url)
        assert result == Path("/output/compras-y-contrataciones")

    def test_convocatoria_collection(self) -> None:
        output = Path("/output")
        url = "https://transparencia.santafeciudad.gov.ar/convocatoria/licitacion-1/"
        result = _dest_folder(output, url)
        assert result == Path("/output/convocatoria")


# ── _sitemap_matches ──────────────────────────────────────────────────────────


class TestSitemapMatches:
    def test_matches_normativa_sitemap(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa-sitemap1.xml"
        assert _sitemap_matches(url, ("normativa",)) is True

    def test_matches_compra_sitemap(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/compra-sitemap2.xml"
        assert _sitemap_matches(url, ("compra",)) is True

    def test_does_not_match_wrong_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa-sitemap1.xml"
        assert _sitemap_matches(url, ("compra",)) is False

    def test_matches_any_of_multiple_collections(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/convocatoria-sitemap1.xml"
        assert _sitemap_matches(url, ("normativa", "compra", "convocatoria")) is True

    def test_non_sitemap_url_does_not_match(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        assert _sitemap_matches(url, ("normativa",)) is False

    def test_empty_collections_never_matches(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa-sitemap1.xml"
        assert _sitemap_matches(url, ()) is False


# ── _parse_sitemap_locs ───────────────────────────────────────────────────────


class TestParseSitemapLocs:
    _SITEMAP_WITH_NS = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page-1/</loc></url>
  <url><loc>https://example.com/page-2/</loc></url>
</urlset>"""

    _SITEMAP_WITHOUT_NS = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://example.com/no-ns-1/</loc></url>
  <url><loc>https://example.com/no-ns-2/</loc></url>
</urlset>"""

    _SITEMAP_INDEX = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/normativa-sitemap1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/compra-sitemap1.xml</loc></sitemap>
</sitemapindex>"""

    def test_parses_locs_with_namespace(self) -> None:
        result = _parse_sitemap_locs(self._SITEMAP_WITH_NS)
        assert result == ["https://example.com/page-1/", "https://example.com/page-2/"]

    def test_parses_locs_without_namespace(self) -> None:
        result = _parse_sitemap_locs(self._SITEMAP_WITHOUT_NS)
        assert result == ["https://example.com/no-ns-1/", "https://example.com/no-ns-2/"]

    def test_parses_sitemap_index(self) -> None:
        result = _parse_sitemap_locs(self._SITEMAP_INDEX)
        assert "https://example.com/normativa-sitemap1.xml" in result
        assert "https://example.com/compra-sitemap1.xml" in result

    def test_returns_empty_list_for_invalid_xml(self) -> None:
        result = _parse_sitemap_locs("this is not xml at all <<<")
        assert result == []

    def test_returns_empty_list_for_empty_urlset(self) -> None:
        xml = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
        result = _parse_sitemap_locs(xml)
        assert result == []

    def test_count_matches_number_of_loc_elements(self) -> None:
        result = _parse_sitemap_locs(self._SITEMAP_WITH_NS)
        expected_count = 2
        assert len(result) == expected_count


# ── is_pending (Santa Fe flavour) ────────────────────────────────────────────


class TestIsPendingSantaFe:
    def test_pending_when_absent(self) -> None:
        assert is_pending("https://example.com/page/", set()) is True

    def test_not_pending_when_completed(self) -> None:
        key = "https://example.com/page/"
        assert is_pending(key, {key}) is False

    def test_not_pending_when_skipped(self) -> None:
        key = "https://example.com/page/"
        assert is_pending(key, {SKIP_PREFIX + key}) is False

    def test_pending_with_unrelated_entries(self) -> None:
        key = "https://example.com/page/"
        assert is_pending(key, {"https://other.com/", SKIP_PREFIX + "https://another.com/"}) is True


# ── extract_wp_pdf_url ────────────────────────────────────────────────────────


class TestExtractWpPdfUrl:
    def test_finds_pdf_in_anchor_href(self) -> None:
        html = (
            '<a href="https://transparencia.santafeciudad.gov.ar'
            '/wp-content/uploads/2024/01/decreto.pdf">Ver PDF</a>'
        )
        result = extract_wp_pdf_url(html, "https://transparencia.santafeciudad.gov.ar/normativa/x/")
        assert result is not None
        assert result.endswith(".pdf")
        assert "/wp-content/uploads/" in result

    def test_finds_pdf_in_relative_href(self) -> None:
        html = '<a href="/wp-content/uploads/2024/02/ordenanza.pdf">Ordenanza</a>'
        page_url = "https://transparencia.santafeciudad.gov.ar/normativa/some-page/"
        result = extract_wp_pdf_url(html, page_url)
        assert result is not None
        assert result.startswith("https://")
        assert result.endswith(".pdf")

    def test_finds_pdf_in_iframe_src(self) -> None:
        html = '<iframe src="/wp-content/uploads/2023/resoluciones.pdf"></iframe>'
        page_url = "https://transparencia.santafeciudad.gov.ar/normativa/some-page/"
        result = extract_wp_pdf_url(html, page_url)
        assert result is not None
        assert "resoluciones.pdf" in result

    def test_finds_pdf_in_data_attribute(self) -> None:
        html = (
            '<object data="/wp-content/uploads/2024/contrato.pdf" type="application/pdf"></object>'
        )
        page_url = "https://transparencia.santafeciudad.gov.ar/normativa/some-page/"
        result = extract_wp_pdf_url(html, page_url)
        assert result is not None
        assert "contrato.pdf" in result

    def test_returns_none_when_no_wp_content_pdf(self) -> None:
        html = '<a href="/other/path/file.pdf">Not a WP PDF</a>'
        result = extract_wp_pdf_url(html, "https://example.com/")
        assert result is None

    def test_returns_none_when_wp_content_but_not_pdf(self) -> None:
        html = '<a href="/wp-content/uploads/image.jpg">Image</a>'
        result = extract_wp_pdf_url(html, "https://example.com/")
        assert result is None

    def test_returns_none_for_empty_html(self) -> None:
        assert extract_wp_pdf_url("", "https://example.com/") is None

    def test_pdf_case_insensitive(self) -> None:
        html = '<a href="/wp-content/uploads/2024/DOC.PDF">PDF</a>'
        result = extract_wp_pdf_url(html, "https://transparencia.santafeciudad.gov.ar/")
        assert result is not None


# ── extract_body_text ─────────────────────────────────────────────────────────


class TestExtractBodyText:
    def test_prefers_entry_content_div(self) -> None:
        html = """
        <html><body>
          <nav>Navigation</nav>
          <div class="entry-content">Main content here</div>
          <footer>Footer</footer>
        </body></html>
        """
        result = extract_body_text(html)
        assert "Main content here" in result
        assert "Navigation" not in result
        assert "Footer" not in result

    def test_prefers_article_over_body_fallback(self) -> None:
        html = """
        <html><body>
          <header>Header</header>
          <article>Article content</article>
          <footer>Footer</footer>
        </body></html>
        """
        result = extract_body_text(html)
        assert "Article content" in result

    def test_falls_back_to_body_when_no_selectors_match(self) -> None:
        html = """
        <html><body>
          <p>Paragraph one</p>
          <p>Paragraph two</p>
        </body></html>
        """
        result = extract_body_text(html)
        assert "Paragraph one" in result
        assert "Paragraph two" in result

    def test_removes_nav_header_footer_from_body_fallback(self) -> None:
        html = """
        <html><body>
          <nav>Should be removed</nav>
          <header>Also removed</header>
          <p>Real content</p>
          <footer>Footer removed</footer>
        </body></html>
        """
        result = extract_body_text(html)
        assert "Real content" in result
        assert "Should be removed" not in result
        assert "Also removed" not in result
        assert "Footer removed" not in result

    def test_removes_script_tags(self) -> None:
        html = """
        <html><body>
          <script>var x = 42;</script>
          <p>Clean text</p>
        </body></html>
        """
        result = extract_body_text(html)
        assert "Clean text" in result
        assert "var x" not in result

    def test_returns_string_for_empty_html(self) -> None:
        result = extract_body_text("")
        assert isinstance(result, str)

    def test_post_content_selector(self) -> None:
        html = """
        <html><body>
          <div class="post-content">Post body text</div>
        </body></html>
        """
        result = extract_body_text(html)
        assert "Post body text" in result

    def test_strips_whitespace(self) -> None:
        html = "<html><body><div class='entry-content'>  trimmed  </div></body></html>"
        result = extract_body_text(html)
        assert result == result.strip()


# ── build_task_list ───────────────────────────────────────────────────────────


class TestBuildTaskList:
    def test_returns_one_task_per_url(self) -> None:
        urls = [
            "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/",
            "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2023/",
        ]
        tasks = build_task_list(Path("/output"), urls)
        expected_count = 2
        assert len(tasks) == expected_count

    def test_task_has_required_keys(self) -> None:
        urls = ["https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"]
        task = build_task_list(Path("/output"), urls)[0]
        assert "key" in task
        assert "page_url" in task
        assert "slug" in task
        assert "dest_folder" in task

    def test_key_equals_page_url(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        task = build_task_list(Path("/output"), [url])[0]
        assert task["key"] == url
        assert task["page_url"] == url

    def test_slug_extracted_correctly(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-0050-2024/"
        task = build_task_list(Path("/output"), [url])[0]
        assert task["slug"] == "ordenanza-0050-2024"

    def test_dest_folder_for_normativa(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-5-2024/"
        task = build_task_list(Path("/output"), [url])[0]
        assert task["dest_folder"] == Path("/output/normativa/decreto_dmm")

    def test_dest_folder_for_non_normativa(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/compras-y-contrataciones/compra-1/"
        task = build_task_list(Path("/output"), [url])[0]
        assert task["dest_folder"] == Path("/output/compras-y-contrataciones")

    def test_empty_url_list_returns_empty_list(self) -> None:
        assert build_task_list(Path("/output"), []) == []

    def test_ordering_preserved(self) -> None:
        urls = [
            "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/",
            "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/",
            "https://transparencia.santafeciudad.gov.ar/convocatoria/licitacion-1/",
        ]
        tasks = build_task_list(Path("/output"), urls)
        assert [t["key"] for t in tasks] == urls
