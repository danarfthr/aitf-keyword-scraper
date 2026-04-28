"""
Crawl4AI-based article crawler for Detik, Kompas, Tribun, CNBC, CNN, Antara.

Uses human-simulation (simulate_user, override_navigator, random UA, scan_full_page)
to bypass CDN-level anti-bot (Cloudflare, DataDome, etc.).
Optional proxy support via CRAWLER_PROXY_URL env var.
"""

import asyncio
import os
import re
import urllib.parse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, ProxyConfig

from shared.shared.constants import MAX_ARTICLES_PER_CRAWLER


# ── Source configurations ───────────────────────────────────────────────────────
# Each source has declarative extraction rules: link pattern, title patterns,
# body pattern (None = use paragraph fallback), and optional URL filter.

_SOURCE_CONFIGS = {
    "detik": {
        "search_url": "https://www.detik.com/search/searchall?query={keyword}",
        "link_pat": r'href="(https?://news\.detik\.com/[^"?]+/d-\d+[^"?]*)"',
        "link_filter": None,
        "title_pats": [
            r'<h1[^>]*\bclass="[^"]*\bdetail__title\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
        "body_pat": r'<div[^>]*\bclass="[^"]*\bdetail__body-text\b[^"]*"[^>]*>(.*?)</div>',
        "body_fallback_paras": False,
    },
    "kompas": {
        "search_url": "https://www.kompas.com/search?q={keyword}",
        "link_pat": r'href="(https?://www\.kompas\.com/[^"?]+)"',
        "link_filter": lambda url: (
            "kompas.com/search" not in url
            and re.search(r'/\w+/.*/\d+', url)
        ),
        "title_pats": [
            r'<h1[^>]*\bclass="[^"]*\bread__title\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
        "body_pat": r'<div[^>]*\bclass="[^"]*\bread__content\b[^"]*"[^>]*>(.*?)</div>',
        "body_fallback_paras": False,
    },
    "tribun": {
        "search_url": "https://www.tribunnews.com/search?q={keyword}",
        "link_pat": r'href="(https?://www\.tribunnews\.com/[^"?]+)"',
        "link_filter": lambda url: (
            "tribunnews.com/search" not in url
            and re.search(r'/\d{4,}/', url)
        ),
        "title_pats": [
            r'<h1[^>]*\bclass="[^"]*\bf40\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
        "body_pat": r'<div[^>]*\bid="article-2"[^>]*>(.*?)</div>',
        "body_fallback_paras": True,
    },
    "cnbc": {
        "search_url": "https://www.cnbcindonesia.com/search?query={keyword}",
        "link_pat": r'href="(https?://www\.cnbcindonesia\.com/news/[^"?]+)"',
        "link_filter": lambda url: (
            "cnbcindonesia.com/search" not in url
            and re.search(r'/news/\d{14}-\d+-\d+/', url)
        ),
        "title_pats": [
            r'<h1[^>]*\bclass="[^"]*\btitle\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
        "body_pat": r'<div[^>]*\bclass="[^"]*\bcontent\b[^"]*"[^>]*>(.*?)</div>',
        "body_fallback_paras": True,
    },
    "cnn": {
        "search_url": "https://www.cnnindonesia.com/search?q={keyword}",
        "link_pat": r'href="(https?://www\.cnnindonesia\.com/[^"?]+)"',
        "link_filter": lambda url: (
            "cnnindonesia.com/search" not in url
            and re.search(r'/\d{14}-\d+/', url)
        ),
        "title_pats": [r'<h1[^>]*>(.*?)</h1>'],
        "body_pat": r'<div[^>]*\bclass="[^"]*\bcontent\b[^"]*"[^>]*>(.*?)</div>',
        "body_fallback_paras": True,
    },
    "antara": {
        "search_url": "https://www.antaranews.com/search?q={keyword}",
        "link_pat": r'href="(https?://www\.antaranews\.com/[^"?]+)"',
        "link_filter": lambda url: (
            "antaranews.com/search" not in url
            and re.search(r'/\d{4}/\d{2}/\d{2}/', url)
        ),
        "title_pats": [r'<h1[^>]*>(.*?)</h1>'],
        "body_pat": r'<div[^>]*\bclass="[^"]*\barticle[-_]?body\b[^"]*"[^>]*>(.*?)</div>',
        "body_fallback_paras": True,
    },
}


# ── Browser / proxy helpers ─────────────────────────────────────────────────────

def _make_browser_cfg() -> BrowserConfig:
    return BrowserConfig(
        headless=True,
        use_persistent_context=False,
        verbose=False,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu",
            "--window-size=1280,720",
        ],
    )


def _maybe_proxy() -> ProxyConfig | None:
    server = os.environ.get("CRAWLER_PROXY_URL", "")
    if not server:
        return None
    username = os.environ.get("CRAWLER_PROXY_USER", "") or None
    password = os.environ.get("CRAWLER_PROXY_PASS", "") or None
    return ProxyConfig(server=server, username=username, password=password)


# ── Crawler configs ─────────────────────────────────────────────────────────────

def _search_cfg() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        wait_until="load",
        delay_before_return_html=6.0,
        page_timeout=90_000,
        simulate_user=True,
        mean_delay=1.5,
        max_range=2.0,
        override_navigator=True,
        scan_full_page=True,
        scroll_delay=0.3,
        remove_overlay_elements=True,
        user_agent_mode="random",
    )


def _article_cfg() -> CrawlerRunConfig:
    return CrawlerRunConfig(
        delay_before_return_html=2.0,
        page_timeout=45_000,
        simulate_user=True,
        override_navigator=True,
        user_agent_mode="random",
    )


# ── Public crawl functions ──────────────────────────────────────────────────────

async def crawl_detik(keyword: str) -> list[dict]:
    return await _crawl_articles(keyword, "detik")


async def crawl_kompas(keyword: str) -> list[dict]:
    return await _crawl_articles(keyword, "kompas")


async def crawl_tribun(keyword: str) -> list[dict]:
    return await _crawl_articles(keyword, "tribun")


async def crawl_cnbc(keyword: str) -> list[dict]:
    return await _crawl_articles(keyword, "cnbc")


async def crawl_cnn(keyword: str) -> list[dict]:
    return await _crawl_articles(keyword, "cnn")


async def crawl_antara(keyword: str) -> list[dict]:
    return await _crawl_articles(keyword, "antara")


# ── Core crawl ─────────────────────────────────────────────────────────────────

async def _crawl_articles(keyword: str, source: str) -> list[dict]:
    from loguru import logger

    cfg = _SOURCE_CONFIGS[source]
    results: list[dict] = []
    seen_urls: set[str] = set()

    search_url = cfg["search_url"].format(keyword=urllib.parse.quote(keyword))
    proxy = _maybe_proxy()

    def search_run_cfg() -> CrawlerRunConfig:
        c = _search_cfg()
        if proxy:
            c.proxy_config = proxy
        return c

    def article_run_cfg() -> CrawlerRunConfig:
        c = _article_cfg()
        if proxy:
            c.proxy_config = proxy
        return c

    try:
        async with AsyncWebCrawler(config=_make_browser_cfg()) as crawler:
            search_result = await crawler.arun(url=search_url, config=search_run_cfg())
            if not getattr(search_result, "success", False):
                search_result = await crawler.arun(url=search_url, config=search_run_cfg())
            if not getattr(search_result, "success", False):
                logger.warning(f"[{source}] Search failed for '{keyword}' after retry")
                return results

            article_links = _extract_links(search_result.html, cfg)
            if article_links:
                logger.info(f"[{source}] '{keyword}': found {len(article_links)} links")
            if not article_links:
                return results

            for link in article_links[:MAX_ARTICLES_PER_CRAWLER]:
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                art_result = await crawler.arun(url=link, config=article_run_cfg())
                if not getattr(art_result, "success", False):
                    continue

                title = _extract_title(art_result.html, cfg)
                body = _extract_body(art_result.html, cfg)

                if title or body:
                    results.append({
                        "source_site": source,
                        "url": link,
                        "title": title,
                        "body": body,
                    })
                    logger.info(f"[{source}] + {title[:50]}")

    except Exception as e:
        logger.warning(f"[{source}] Exception on '{keyword}': {e}")

    return results


# ── HTML extraction helpers ────────────────────────────────────────────────────

def _extract_links(html: str, cfg: dict) -> list[str]:
    """Extract article URLs matching source's link pattern and filter."""
    links: list[str] = []
    seen: set[str] = set()
    link_filter = cfg["link_filter"]

    for m in re.findall(cfg["link_pat"], html, re.IGNORECASE):
        url = m.rstrip() if isinstance(m, str) else m.group(0).rstrip()
        if link_filter is not None and not link_filter(url):
            continue
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _extract_title(html: str, cfg: dict) -> str:
    """Extract article <h1> title using first matching pattern."""
    for pat in cfg["title_pats"]:
        m = re.search(pat, html, re.DOTALL)
        if m:
            return _strip_tags(m.group(1))
    return ""


def _extract_body(html: str, cfg: dict) -> str:
    """Extract body via source-specific pattern or paragraph fallback."""
    body_pat = cfg.get("body_pat")
    if body_pat:
        m = re.search(body_pat, html, re.DOTALL)
        if m:
            return _strip_tags(m.group(1))

    if cfg.get("body_fallback_paras"):
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        if paras:
            return " ".join(_strip_tags(p) for p in paras[:15] if _strip_tags(p))
    return ""


def _strip_tags(text: str) -> str:
    text = re.sub(r'<[^>]+>', " ", text)
    text = re.sub(r'\s+', " ", text)
    return text.strip()
