"""Web crawler and HTML loader.

This module is the URL-ingestion counterpart to `pdf_loader`. It fetches web
pages (optionally via a rotating proxy pool), strips HTML to plain text,
chunks the text, and pushes everything into ChromaDB so the existing RAG
engine can query it with zero changes.

Design notes:
- **Isolated from the query hot path.** Nothing here runs during
  `/api/query`. The query path just reads ChromaDB, which doesn't care
  whether a chunk came from a PDF or a web page.
- **SSRF-hard.** Only http/https schemes; private IPv4/IPv6 ranges, loopback,
  link-local (including AWS metadata 169.254.169.254) and multicast are
  refused after DNS resolution so an attacker can't hide a private IP behind
  a public hostname.
- **Rotates proxies and User-Agent strings** per request when proxies are
  configured, plus retries with exponential backoff on transient failures.
- **Respects `robots.txt`** by default (opt-out via env var).
- **Bounded BFS crawl** with same-origin constraint, configurable depth and
  page cap; when the site has a `sitemap.xml` we use it as a shortcut.
- **PDF short-circuit:** if the URL serves a PDF, we hand it to the existing
  `load_pdf` path so crawled PDFs get the same table/text extraction.
"""

from __future__ import annotations

import ipaddress
import random
import re
import socket
import tempfile
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    SCRAPE_CONCURRENCY,
    SCRAPE_MAX_BYTES,
    SCRAPE_MAX_DEPTH,
    SCRAPE_MAX_PAGES,
    SCRAPE_POLITE_DELAY_MS,
    SCRAPE_PROXIES,
    SCRAPE_RESPECT_ROBOTS,
    SCRAPE_RETRIES,
    SCRAPE_TIMEOUT_SEC,
    SCRAPE_USER_AGENTS,
)

# ── SSRF guard ──────────────────────────────────────────────────────────────

_ALLOWED_SCHEMES = {"http", "https"}


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → refuse
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_host_safely(host: str) -> tuple[bool, str]:
    """Resolve the host; reject if any resolved address is non-public."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"
    for info in infos:
        addr = info[4][0]
        if _is_private_ip(addr):
            return False, f"Host resolves to a private/loopback address ({addr})"
    return True, "ok"


def validate_url(url: str) -> tuple[bool, str]:
    """Return (is_safe, reason). Blocks non-HTTP(S), private networks, local DNS."""
    if not url or not isinstance(url, str):
        return False, "URL is empty"
    try:
        p = urllib.parse.urlparse(url.strip())
    except Exception as e:
        return False, f"Malformed URL: {e}"
    if p.scheme.lower() not in _ALLOWED_SCHEMES:
        return False, f"Only http(s) URLs are allowed (got '{p.scheme}')"
    if not p.hostname:
        return False, "URL has no hostname"
    return _resolve_host_safely(p.hostname)


# ── HTTP session with rotation + retries ────────────────────────────────────


class Fetcher:
    """Thread-unsafe HTTP session that rotates proxies + UAs and retries."""

    def __init__(
        self,
        proxies: list[str] | None = None,
        user_agents: list[str] | None = None,
        timeout: int = SCRAPE_TIMEOUT_SEC,
        max_bytes: int = SCRAPE_MAX_BYTES,
        retries: int = SCRAPE_RETRIES,
    ):
        self.proxies = list(proxies) if proxies else list(SCRAPE_PROXIES)
        self.user_agents = list(user_agents) if user_agents else list(SCRAPE_USER_AGENTS)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.retries = retries
        self.session = requests.Session()
        self._proxy_index = 0

    def _next_proxy(self) -> dict | None:
        if not self.proxies:
            return None
        proxy = self.proxies[self._proxy_index % len(self.proxies)]
        self._proxy_index += 1
        return {"http": proxy, "https": proxy}

    def _headers(self, referer: str | None = None) -> dict[str, str]:
        ua = random.choice(self.user_agents) if self.user_agents else "scout-bot/1.0"
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def fetch(self, url: str, referer: str | None = None) -> tuple[bytes, str, str]:
        """Fetch URL bytes, return (body, final_url, content_type).

        Raises RuntimeError on failure after retries. Streams the response and
        aborts if it exceeds `max_bytes`.
        """
        last_err: str = ""
        for attempt in range(self.retries + 1):
            try:
                proxy = self._next_proxy()
                resp = self.session.get(
                    url,
                    headers=self._headers(referer),
                    timeout=self.timeout,
                    proxies=proxy,
                    stream=True,
                    allow_redirects=True,
                )
                # After redirects, re-validate the final host.
                final_url = resp.url
                ok, reason = validate_url(final_url)
                if not ok:
                    resp.close()
                    raise RuntimeError(f"redirect target blocked: {reason}")

                if resp.status_code >= 400:
                    last_err = f"HTTP {resp.status_code}"
                    resp.close()
                    # 5xx is retryable; 4xx generally isn't.
                    if resp.status_code < 500:
                        break
                    raise RuntimeError(last_err)

                content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                # Early size check via Content-Length
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit() and int(cl) > self.max_bytes:
                    resp.close()
                    raise RuntimeError(f"Content-Length {cl} exceeds {self.max_bytes}")

                body = bytearray()
                for chunk in resp.iter_content(chunk_size=16 * 1024):
                    if not chunk:
                        continue
                    body.extend(chunk)
                    if len(body) > self.max_bytes:
                        resp.close()
                        raise RuntimeError(f"Response exceeded {self.max_bytes} bytes")
                resp.close()
                return bytes(body), final_url, content_type
            except (requests.RequestException, RuntimeError) as e:
                last_err = str(e)
                if attempt < self.retries:
                    # Exponential backoff with jitter.
                    sleep_s = (2 ** attempt) * 0.4 + random.random() * 0.3
                    time.sleep(sleep_s)
                    continue
                break
        raise RuntimeError(f"fetch failed for {url}: {last_err}")


# ── HTML → text ─────────────────────────────────────────────────────────────


_STRIP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "nav", "footer", "header", "aside", "form")


def extract_text_and_links(html: bytes, base_url: str) -> tuple[str, str, list[str]]:
    """Return (title, clean_text, outbound_links) from an HTML document."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    title = (soup.title.string.strip() if soup.title and soup.title.string else "")

    # Prefer the main/article body if present; fall back to body.
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Collect same-page outbound links (absolute URLs).
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        links.append(urllib.parse.urljoin(base_url, href))

    return title, text, links


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    if not text:
        return []
    if len(text) <= chunk_size:
        return [{"text": text.strip(), "chunk_index": 0}]

    chunks, start, idx = [], 0, 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            last_period = text.rfind(".", start, end)
            last_newline = text.rfind("\n", start, end)
            bp = max(last_period, last_newline)
            if bp > start + chunk_size // 2:
                end = bp + 1
        body = text[start:end].strip()
        if body:
            chunks.append({"text": body, "chunk_index": idx})
            idx += 1
        start = end - overlap
    return chunks


# ── Sitemap + robots.txt ────────────────────────────────────────────────────


def _robots_checker(base_url: str) -> urllib.robotparser.RobotFileParser | None:
    if not SCRAPE_RESPECT_ROBOTS:
        return None
    try:
        parts = urllib.parse.urlsplit(base_url)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{parts.scheme}://{parts.netloc}/robots.txt")
        rp.read()
        return rp
    except Exception:
        return None


def _robot_allowed(rp, url: str, ua: str) -> bool:
    if rp is None:
        return True
    try:
        return rp.can_fetch(ua, url)
    except Exception:
        return True


def parse_sitemap(sitemap_bytes: bytes) -> list[str]:
    """Parse a sitemap or sitemap index and return a flat list of page URLs."""
    urls: list[str] = []
    try:
        root = ET.fromstring(sitemap_bytes)
    except ET.ParseError:
        return urls
    # Strip namespaces for convenience.
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    # Sitemap index — nested sitemaps.
    for sitemap in root.findall("sm:sitemap", ns):
        loc = sitemap.find("sm:loc", ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    # Leaf sitemap — page URLs.
    for url_el in root.findall("sm:url", ns):
        loc = url_el.find("sm:loc", ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


def discover_via_sitemap(
    fetcher: Fetcher,
    base_url: str,
    path_filter: str | None,
    max_pages: int,
) -> list[str]:
    """Try sitemap.xml. Returns an ordered list of candidate page URLs."""
    parts = urllib.parse.urlsplit(base_url)
    sitemap_url = f"{parts.scheme}://{parts.netloc}/sitemap.xml"
    try:
        body, final_url, ctype = fetcher.fetch(sitemap_url)
    except Exception:
        return []
    candidates: list[str] = []
    queue: deque[str] = deque([sitemap_url])
    seen: set[str] = set()
    while queue and len(candidates) < max_pages * 3:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        try:
            body, _, _ = fetcher.fetch(current) if current != sitemap_url else (body, final_url, ctype)
        except Exception:
            continue
        for url in parse_sitemap(body):
            if url.endswith(".xml"):
                queue.append(url)
            else:
                candidates.append(url)
    if path_filter:
        pf = path_filter.strip()
        candidates = [u for u in candidates if pf in urllib.parse.urlsplit(u).path]
    # Same-host only.
    host = parts.netloc
    candidates = [u for u in candidates if urllib.parse.urlsplit(u).netloc == host]
    # De-dup while preserving order.
    seen2: set[str] = set()
    deduped: list[str] = []
    for u in candidates:
        if u not in seen2:
            seen2.add(u)
            deduped.append(u)
    return deduped[:max_pages]


# ── BFS crawler ─────────────────────────────────────────────────────────────


@dataclass
class CrawlResult:
    pages: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _same_origin(a: str, b: str) -> bool:
    return urllib.parse.urlsplit(a).netloc == urllib.parse.urlsplit(b).netloc


def crawl(
    start_url: str,
    max_pages: int = SCRAPE_MAX_PAGES,
    max_depth: int = SCRAPE_MAX_DEPTH,
    path_filter: str | None = None,
    use_sitemap: bool = True,
    fetcher: Fetcher | None = None,
) -> CrawlResult:
    """Bounded BFS crawl from `start_url`, same-origin, with a page cap.

    If the host publishes a sitemap we use it to seed the queue (ordered by
    sitemap position) — dramatically faster on well-structured sites like
    Wikipedia or Apple support.
    """
    result = CrawlResult()
    ok, reason = validate_url(start_url)
    if not ok:
        result.errors.append({"url": start_url, "error": reason})
        return result

    fetcher = fetcher or Fetcher()
    rp = _robots_checker(start_url)
    ua = fetcher.user_agents[0] if fetcher.user_agents else "scout-bot/1.0"

    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    if use_sitemap:
        for u in discover_via_sitemap(fetcher, start_url, path_filter, max_pages):
            queue.append((u, 0))

    # Always include the start URL as a first-class candidate.
    queue.appendleft((start_url, 0))

    while queue and len(result.pages) < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        if not _same_origin(url, start_url):
            result.skipped.append(url)
            continue
        if path_filter and path_filter not in urllib.parse.urlsplit(url).path:
            result.skipped.append(url)
            continue
        if not _robot_allowed(rp, url, ua):
            result.skipped.append(url)
            continue

        try:
            body, final_url, ctype = fetcher.fetch(url)
        except Exception as e:
            result.errors.append({"url": url, "error": str(e)[:200]})
            continue

        if "html" not in ctype and "xml" not in ctype:
            # PDFs and other file types are out of scope for the crawler
            # body; callers can upload them separately via the URL-as-PDF path.
            result.skipped.append(final_url)
            continue

        title, text, links = extract_text_and_links(body, final_url)
        if text:
            result.pages.append({
                "url": final_url,
                "title": title,
                "text": text,
                "depth": depth,
            })

        # Enqueue outbound links from this page if we have depth budget.
        if depth + 1 <= max_depth:
            for link in links:
                if link in visited:
                    continue
                queue.append((link, depth + 1))

        if SCRAPE_POLITE_DELAY_MS > 0:
            time.sleep(SCRAPE_POLITE_DELAY_MS / 1000.0)

    return result


# ── ChromaDB ingestion ──────────────────────────────────────────────────────


def _embedder():
    """Lazy-import the embedder so the crawler itself has no ML deps."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def load_url(
    url: str,
    source_name: str,
    chroma_collection,
    duckdb_conn=None,
    max_pages: int = SCRAPE_MAX_PAGES,
    max_depth: int = SCRAPE_MAX_DEPTH,
    path_filter: str | None = None,
    crawl_multi: bool = True,
) -> dict:
    """Fetch a URL (or crawl multiple pages from it) and index chunks in Chroma.

    Returns metadata compatible with the existing source registry.
    """
    ok, reason = validate_url(url)
    if not ok:
        return {"source_name": source_name, "source_type": "url", "error": reason}

    fetcher = Fetcher()

    # PDF short-circuit — route through the existing PDF loader.
    try:
        probe = fetcher.session.head(
            url,
            headers=fetcher._headers(),
            timeout=fetcher.timeout,
            allow_redirects=True,
        )
        probe_ct = probe.headers.get("Content-Type", "").lower()
    except Exception:
        probe_ct = ""
    if "application/pdf" in probe_ct or url.lower().split("?", 1)[0].endswith(".pdf"):
        return _load_remote_pdf(url, source_name, chroma_collection, duckdb_conn, fetcher)

    if crawl_multi:
        result = crawl(
            url,
            max_pages=max_pages,
            max_depth=max_depth,
            path_filter=path_filter,
            fetcher=fetcher,
        )
    else:
        single = _fetch_single(url, fetcher)
        result = CrawlResult(pages=[single] if single else [], errors=[])

    if not result.pages:
        err = result.errors[0]["error"] if result.errors else "no pages retrieved"
        return {"source_name": source_name, "source_type": "url", "error": err}

    # Chunk + embed + store.
    all_chunks: list[dict] = []
    for page in result.pages:
        for c in _chunk_text(page["text"]):
            all_chunks.append({
                "text": c["text"],
                "metadata": {
                    "source": source_name,
                    "url": page["url"],
                    "title": page["title"][:200],
                    "chunk_index": c["chunk_index"],
                    "type": "web",
                },
            })

    if not all_chunks:
        return {"source_name": source_name, "source_type": "url", "error": "no text extracted"}

    model = _embedder()
    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, show_progress_bar=False).tolist()
    ids = [f"{source_name}::{i}" for i in range(len(all_chunks))]
    chroma_collection.add(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in all_chunks],
    )

    return {
        "source_name": source_name,
        "source_type": "url",
        "url": url,
        "pages_crawled": len(result.pages),
        "chunks": len(all_chunks),
        "errors": result.errors[:10],
    }


def _fetch_single(url: str, fetcher: Fetcher) -> dict | None:
    try:
        body, final_url, ctype = fetcher.fetch(url)
    except Exception:
        return None
    if "html" not in ctype and "xml" not in ctype:
        return None
    title, text, _ = extract_text_and_links(body, final_url)
    if not text:
        return None
    return {"url": final_url, "title": title, "text": text, "depth": 0}


def _load_remote_pdf(
    url: str,
    source_name: str,
    chroma_collection,
    duckdb_conn,
    fetcher: Fetcher,
) -> dict:
    """Download a PDF and hand off to the existing PDF loader."""
    from src.ingestion.pdf_loader import load_pdf

    try:
        body, _, _ = fetcher.fetch(url)
    except Exception as e:
        return {"source_name": source_name, "source_type": "url", "error": str(e)[:200]}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    meta = load_pdf(tmp_path, source_name, chroma_collection, duckdb_conn)
    meta["source_type"] = "url"
    meta["url"] = url
    return meta
