"""P1 tests — pure functions in scrapper/downloader.py (no I/O, no async, no mocks)."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from scrapper.downloader import (
    SKIP_PREFIX,
    _apply_migration,
    _is_pdf_url,
    _search_all_attrs,
    _search_raw_html,
    _search_tagged_elements,
    build_normativa_pdf_url,
    extract_pdf_url_from_html,
    is_pending,
    normalize_url,
    sanitize,
)

# ── normalize_url ────────────────────────────────────────────


class TestNormalizeUrl:
    def test_empty_string(self) -> None:
        assert normalize_url("") is None

    def test_whitespace_only(self) -> None:
        assert normalize_url("   ") is None

    def test_adds_http_to_www(self) -> None:
        assert normalize_url("www.rosario.gob.ar/path") == "http://www.rosario.gob.ar/path"

    def test_adds_https_to_ssl(self) -> None:
        assert normalize_url("ssl.rosario.gob.ar/path") == "https://ssl.rosario.gob.ar/path"

    def test_strips_leading_slash_www(self) -> None:
        assert normalize_url("/www.rosario.gob.ar/path") == "http://www.rosario.gob.ar/path"

    def test_strips_leading_slash_ssl(self) -> None:
        assert normalize_url("/ssl.rosario.gob.ar/path") == "https://ssl.rosario.gob.ar/path"

    def test_preserves_existing_http(self) -> None:
        url = "http://www.rosario.gob.ar/normativa"
        assert normalize_url(url) == url

    def test_preserves_existing_https(self) -> None:
        url = "https://www.rosario.gob.ar/normativa"
        assert normalize_url(url) == url

    def test_strips_surrounding_whitespace(self) -> None:
        assert normalize_url("  http://example.com  ") == "http://example.com"

    def test_bare_word_gets_scheme_added(self) -> None:
        result = normalize_url("not-a-url")
        assert result == "http://not-a-url"

    def test_slash_only_returns_none(self) -> None:
        assert normalize_url("/") is None


# ── _is_pdf_url ──────────────────────────────────────────────


class TestIsPdfUrl:
    def test_ver_archivo(self) -> None:
        assert _is_pdf_url("/normativa/verArchivo?id=123") is True

    def test_get_pdf(self) -> None:
        assert _is_pdf_url("/normativa/getPdf?id=456") is True

    def test_documento_do(self) -> None:
        assert _is_pdf_url("/normativa/documento.do?id=789") is True

    def test_pdf_extension(self) -> None:
        assert _is_pdf_url("https://example.com/file.pdf") is True

    def test_pdf_extension_uppercase(self) -> None:
        assert _is_pdf_url("https://example.com/file.PDF") is True

    def test_non_pdf_url(self) -> None:
        assert _is_pdf_url("https://example.com/page.html") is False

    def test_empty_string(self) -> None:
        assert _is_pdf_url("") is False


# ── _search_tagged_elements ──────────────────────────────────


class TestSearchTaggedElements:
    def test_finds_pdf_in_anchor_href(self) -> None:

        html = '<a href="/normativa/verArchivo?id=99">Download</a>'
        soup = BeautifulSoup(html, "lxml")
        result = _search_tagged_elements(soup, lambda u: f"https://base{u}")
        assert result == "https://base/normativa/verArchivo?id=99"

    def test_finds_pdf_in_iframe_src(self) -> None:

        html = '<iframe src="/normativa/getPdf?id=42"></iframe>'
        soup = BeautifulSoup(html, "lxml")
        result = _search_tagged_elements(soup, lambda u: f"https://base{u}")
        assert result == "https://base/normativa/getPdf?id=42"

    def test_finds_pdf_in_embed_src(self) -> None:

        html = '<embed src="/doc.pdf">'
        soup = BeautifulSoup(html, "lxml")
        result = _search_tagged_elements(soup, lambda u: f"https://base{u}")
        assert result == "https://base/doc.pdf"

    def test_returns_none_when_no_pdf(self) -> None:

        html = '<a href="/page.html">Link</a>'
        soup = BeautifulSoup(html, "lxml")
        assert _search_tagged_elements(soup, lambda u: u) is None


# ── _search_all_attrs ────────────────────────────────────────


class TestSearchAllAttrs:
    def test_finds_pdf_in_data_attribute(self) -> None:

        html = '<div data-url="/normativa/verArchivo?id=55">content</div>'
        soup = BeautifulSoup(html, "lxml")
        result = _search_all_attrs(soup, lambda u: f"https://base{u}")
        assert result == "https://base/normativa/verArchivo?id=55"

    def test_returns_none_when_no_pdf(self) -> None:

        html = "<div data-url='/page.html'>content</div>"
        soup = BeautifulSoup(html, "lxml")
        assert _search_all_attrs(soup, lambda u: u) is None


# ── _search_raw_html ─────────────────────────────────────────


class TestSearchRawHtml:
    def test_finds_ver_archivo_in_script(self) -> None:
        html = """<script>var url = "/normativa/verArchivo?id=77";</script>"""
        result = _search_raw_html(html, lambda u: f"https://base{u}")
        assert result == "https://base/normativa/verArchivo?id=77"

    def test_finds_get_pdf_in_script(self) -> None:
        html = """<script>window.open('/normativa/getPdf?id=88');</script>"""
        result = _search_raw_html(html, lambda u: f"https://base{u}")
        assert result == "https://base/normativa/getPdf?id=88"

    def test_returns_none_when_no_match(self) -> None:
        html = "<script>var x = 42;</script>"
        assert _search_raw_html(html, lambda u: u) is None


# ── extract_pdf_url_from_html ────────────────────────────────


class TestExtractPdfUrlFromHtml:
    def test_extracts_from_anchor(self) -> None:
        html = '<html><body><a href="/normativa/verArchivo?id=100">PDF</a></body></html>'
        result = extract_pdf_url_from_html(html, "https://www.rosario.gob.ar/page")
        assert result == "https://www.rosario.gob.ar/normativa/verArchivo?id=100"

    def test_extracts_absolute_url(self) -> None:
        html = '<a href="https://cdn.example.com/doc.pdf">PDF</a>'
        result = extract_pdf_url_from_html(html, "https://www.rosario.gob.ar/page")
        assert result == "https://cdn.example.com/doc.pdf"

    def test_falls_back_to_raw_html_regex(self) -> None:
        html = """<script>var u = "/normativa/verArchivo?id=200";</script>"""
        result = extract_pdf_url_from_html(html, "https://www.rosario.gob.ar/page")
        assert result == "https://www.rosario.gob.ar/normativa/verArchivo?id=200"

    def test_returns_none_when_no_pdf(self) -> None:
        html = "<html><body><p>No documents here</p></body></html>"
        assert extract_pdf_url_from_html(html, "https://example.com") is None


# ── build_normativa_pdf_url ──────────────────────────────────


class TestBuildNormativaPdfUrl:
    def test_extracts_id_normativa(self) -> None:
        url = "https://www.rosario.gob.ar/normativa/visualExterna.do?idNormativa=12345"
        result = build_normativa_pdf_url(url)
        assert result == (
            "https://www.rosario.gob.ar/normativa/verArchivo?tipo=pdf&id=12345&modo=attachment"
        )

    def test_returns_none_without_id(self) -> None:
        url = "https://www.rosario.gob.ar/normativa/visualExterna.do?other=abc"
        assert build_normativa_pdf_url(url) is None

    def test_returns_none_for_empty_query(self) -> None:
        assert build_normativa_pdf_url("https://example.com/page") is None

    def test_handles_multiple_query_params(self) -> None:
        url = "https://www.rosario.gob.ar/normativa/visualExterna.do?foo=1&idNormativa=999&bar=2"
        result = build_normativa_pdf_url(url)
        assert result is not None
        assert "id=999" in result


# ── sanitize ─────────────────────────────────────────────────


class TestSanitize:
    def test_replaces_invalid_chars(self) -> None:
        assert sanitize('file<name>:with"bad|chars') == "file_name__with_bad_chars"

    def test_replaces_backslash(self) -> None:
        assert sanitize("path\\to\\file") == "path_to_file"

    def test_strips_whitespace(self) -> None:
        assert sanitize("  clean  ") == "clean"

    def test_preserves_valid_chars(self) -> None:
        assert sanitize("boletin_123_2024") == "boletin_123_2024"

    def test_question_mark(self) -> None:
        assert sanitize("file?.pdf") == "file_.pdf"

    def test_asterisk(self) -> None:
        assert sanitize("file*.pdf") == "file_.pdf"


# ── is_pending ───────────────────────────────────────────────


class TestIsPending:
    def test_pending_when_absent(self) -> None:
        assert is_pending("file.pdf", set()) is True

    def test_not_pending_when_completed(self) -> None:
        assert is_pending("file.pdf", {"file.pdf"}) is False

    def test_not_pending_when_skipped(self) -> None:
        assert is_pending("file.pdf", {SKIP_PREFIX + "file.pdf"}) is False

    def test_pending_with_unrelated_entries(self) -> None:
        assert is_pending("file.pdf", {"other.pdf", SKIP_PREFIX + "another.pdf"}) is True


# ── _apply_migration ─────────────────────────────────────────


class TestApplyMigration:
    def test_unblocks_boletin_html_skips(self) -> None:
        tasks = [{"key": "bol.pdf", "link_type": "boletin_html"}]
        done: set[str] = {SKIP_PREFIX + "bol.pdf", "other.pdf"}
        _apply_migration(tasks, done)
        assert SKIP_PREFIX + "bol.pdf" not in done
        assert "other.pdf" in done

    def test_unblocks_html_to_pdf_skips(self) -> None:
        tasks = [{"key": "page.pdf", "link_type": "html_to_pdf"}]
        done: set[str] = {SKIP_PREFIX + "page.pdf"}
        _apply_migration(tasks, done)
        assert SKIP_PREFIX + "page.pdf" not in done

    def test_leaves_other_link_types_alone(self) -> None:
        tasks = [{"key": "norm.pdf", "link_type": "normativa"}]
        done: set[str] = {SKIP_PREFIX + "norm.pdf"}
        _apply_migration(tasks, done)
        assert SKIP_PREFIX + "norm.pdf" in done

    def test_no_op_when_nothing_to_unblock(self) -> None:
        tasks = [{"key": "x.pdf", "link_type": "direct_pdf"}]
        done: set[str] = {"x.pdf"}
        _apply_migration(tasks, done)
        assert done == {"x.pdf"}

    @pytest.mark.parametrize("link_type", ["boletin_html", "html_to_pdf"])
    def test_unblocks_only_matching_keys(self, link_type: str) -> None:
        tasks = [
            {"key": "a.pdf", "link_type": link_type},
            {"key": "b.pdf", "link_type": "normativa"},
        ]
        done: set[str] = {SKIP_PREFIX + "a.pdf", SKIP_PREFIX + "b.pdf"}
        _apply_migration(tasks, done)
        assert SKIP_PREFIX + "a.pdf" not in done
        assert SKIP_PREFIX + "b.pdf" in done
