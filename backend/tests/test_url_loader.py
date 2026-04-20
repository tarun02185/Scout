"""Tests for the URL/website crawler."""

from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.url_loader import (
    Fetcher,
    _chunk_text,
    _is_private_ip,
    extract_text_and_links,
    parse_sitemap,
    validate_url,
)


# ── SSRF guard ──────────────────────────────────────────────────────────────


class TestSSRFGuard:
    def test_blocks_file_scheme(self):
        ok, _ = validate_url("file:///etc/passwd")
        assert ok is False

    def test_blocks_javascript_scheme(self):
        ok, _ = validate_url("javascript:alert(1)")
        assert ok is False

    def test_blocks_ftp(self):
        ok, _ = validate_url("ftp://example.com/")
        assert ok is False

    def test_blocks_empty(self):
        ok, _ = validate_url("")
        assert ok is False

    def test_blocks_missing_host(self):
        ok, _ = validate_url("http://")
        assert ok is False

    @patch("src.ingestion.url_loader.socket.getaddrinfo")
    def test_blocks_localhost_by_dns(self, gai):
        gai.return_value = [(0, 0, 0, "", ("127.0.0.1", 0))]
        ok, reason = validate_url("http://localhost/")
        assert ok is False
        assert "private" in reason.lower() or "loopback" in reason.lower()

    @patch("src.ingestion.url_loader.socket.getaddrinfo")
    def test_blocks_private_subnet(self, gai):
        gai.return_value = [(0, 0, 0, "", ("10.0.0.5", 0))]
        ok, _ = validate_url("http://internal.corp/")
        assert ok is False

    @patch("src.ingestion.url_loader.socket.getaddrinfo")
    def test_blocks_aws_metadata(self, gai):
        gai.return_value = [(0, 0, 0, "", ("169.254.169.254", 0))]
        ok, _ = validate_url("http://metadata.aws/")
        assert ok is False

    @patch("src.ingestion.url_loader.socket.getaddrinfo")
    def test_allows_public_ip(self, gai):
        gai.return_value = [(0, 0, 0, "", ("93.184.216.34", 0))]  # example.com
        ok, _ = validate_url("https://example.com/")
        assert ok is True

    def test_is_private_ip(self):
        assert _is_private_ip("127.0.0.1") is True
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("169.254.169.254") is True
        assert _is_private_ip("::1") is True
        assert _is_private_ip("93.184.216.34") is False


# ── HTML parsing ────────────────────────────────────────────────────────────


class TestHTMLParsing:
    def test_extracts_title_and_text(self):
        html = b"""<html><head><title>Hi</title></head>
            <body><main><p>Hello <b>world</b>.</p></main></body></html>"""
        title, text, links = extract_text_and_links(html, "https://x.com/")
        assert title == "Hi"
        assert "Hello" in text and "world" in text

    def test_strips_scripts_and_style(self):
        html = b"""<html><body>
            <script>alert('x')</script>
            <style>.a{color:red}</style>
            <p>Real content</p>
            </body></html>"""
        _, text, _ = extract_text_and_links(html, "https://x.com/")
        assert "alert" not in text
        assert "color:red" not in text
        assert "Real content" in text

    def test_resolves_relative_links(self):
        html = b"""<html><body>
            <a href="/about">About</a>
            <a href="contact.html">Contact</a>
            <a href="https://other.com/x">Ext</a>
            <a href="#top">Top</a>
            <a href="mailto:x@y.com">Mail</a>
            </body></html>"""
        _, _, links = extract_text_and_links(html, "https://x.com/page")
        assert "https://x.com/about" in links
        assert "https://x.com/contact.html" in links
        assert "https://other.com/x" in links
        # Anchors and mailto filtered out.
        assert not any(l.startswith("#") for l in links)
        assert not any("mailto:" in l for l in links)


# ── Chunking ────────────────────────────────────────────────────────────────


class TestChunking:
    def test_short_text_one_chunk(self):
        chunks = _chunk_text("short sentence.")
        assert len(chunks) == 1

    def test_long_text_multiple_chunks(self):
        text = ("This is a sentence. " * 200).strip()
        chunks = _chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) >= 2
        assert all(c["text"] for c in chunks)

    def test_empty_text_no_chunks(self):
        assert _chunk_text("") == []


# ── Sitemap parsing ─────────────────────────────────────────────────────────


class TestSitemap:
    def test_parses_leaf_sitemap(self):
        xml = b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://x.com/a</loc></url>
          <url><loc>https://x.com/b</loc></url>
        </urlset>"""
        urls = parse_sitemap(xml)
        assert urls == ["https://x.com/a", "https://x.com/b"]

    def test_parses_sitemap_index(self):
        xml = b"""<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://x.com/sitemap-1.xml</loc></sitemap>
          <sitemap><loc>https://x.com/sitemap-2.xml</loc></sitemap>
        </sitemapindex>"""
        urls = parse_sitemap(xml)
        assert "https://x.com/sitemap-1.xml" in urls
        assert "https://x.com/sitemap-2.xml" in urls

    def test_malformed_sitemap(self):
        urls = parse_sitemap(b"not xml")
        assert urls == []


# ── Fetcher rotation ────────────────────────────────────────────────────────


class TestFetcherRotation:
    def test_rotates_proxies(self):
        f = Fetcher(proxies=["http://p1:3128", "http://p2:3128", "http://p3:3128"])
        p1 = f._next_proxy()
        p2 = f._next_proxy()
        p3 = f._next_proxy()
        p4 = f._next_proxy()
        assert p1["http"] == "http://p1:3128"
        assert p2["http"] == "http://p2:3128"
        assert p3["http"] == "http://p3:3128"
        assert p4["http"] == "http://p1:3128", "should wrap around"

    def test_no_proxy_returns_none(self):
        f = Fetcher(proxies=[])
        assert f._next_proxy() is None

    def test_rotates_user_agents(self):
        f = Fetcher(user_agents=["UA1", "UA2"])
        uas = {f._headers()["User-Agent"] for _ in range(20)}
        # Over many samples we expect to see both.
        assert uas.issubset({"UA1", "UA2"})

    def test_headers_include_standard_fields(self):
        f = Fetcher(user_agents=["test-ua"])
        h = f._headers(referer="https://ref.com/")
        assert h["User-Agent"] == "test-ua"
        assert "Accept" in h
        assert h["Referer"] == "https://ref.com/"
