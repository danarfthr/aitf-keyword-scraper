"""
Crawl4AI-based article crawler for Detik, Kompas, Tribun.

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

def _make_browser_cfg() -> BrowserConfig:
    """
    Fresh (non-persistent) browser context with low-level automation flags disabled.
    NOTE: avoid enable_stealth + magic=True — fingerprint modifications can
    trigger blocking scripts on sites with aggressive anti-bot (Cloudflare/DataDome).
    Human-simulation is applied at the CrawlerRunConfig level instead.
    """
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
    """Return a ProxyConfig if CRAWLER_PROXY_URL env var is set, else None."""
    server = os.environ.get("CRAWLER_PROXY_URL", "")
    if not server:
        return None
    username = os.environ.get("CRAWLER_PROXY_USER", "") or None
    password = os.environ.get("CRAWLER_PROXY_PASS", "") or None
    return ProxyConfig(server=server, username=username, password=password)


def _search_cfg() -> CrawlerRunConfig:
    """
    Config for search result pages.
    Uses human-simulation flags + random user agent to avoid anti-bot.
    scan_full_page replaces manual JS scroll.
    """
    return CrawlerRunConfig(
        wait_until="load",
        delay_before_return_html=6.0,
        page_timeout=90_000,
        # Human-like behaviour
        simulate_user=True,
        mean_delay=1.5,
        max_range=2.0,
        override_navigator=True,
        # Auto-scroll full page (replaces manual JS scroll)
        scan_full_page=True,
        scroll_delay=0.3,
        # Dismiss cookie/bot-check overlays
        remove_overlay_elements=True,
        # Randomise fingerprint
        user_agent_mode="random",
    )


def _article_cfg() -> CrawlerRunConfig:
    """Config for individual article pages."""
    return CrawlerRunConfig(
        delay_before_return_html=2.0,
        page_timeout=45_000,
        simulate_user=True,
        override_navigator=True,
        user_agent_mode="random",
    )


# ── Per-site search URLs ───────────────────────────────────────────────────────

_DETIK_SEARCH = "https://www.detik.com/search/searchall?query={keyword}"

_KOMPAS_SEARCH = "https://www.kompas.com/search?q={keyword}"

_TRIBUN_SEARCH = "https://www.tribunnews.com/search?q={keyword}"


async def crawl_detik(keyword: str) -> list[dict]:
    url = _DETIK_SEARCH.format(keyword=urllib.parse.quote(keyword))
    return await _crawl_articles(keyword, "detik", url)


async def crawl_kompas(keyword: str) -> list[dict]:
    url = _KOMPAS_SEARCH.format(keyword=urllib.parse.quote(keyword))
    return await _crawl_articles(keyword, "kompas", url)


async def crawl_tribun(keyword: str) -> list[dict]:
    url = _TRIBUN_SEARCH.format(keyword=urllib.parse.quote(keyword))
    return await _crawl_articles(keyword, "tribun", url)


# ── Core crawl ─────────────────────────────────────────────────────────────────

async def _crawl_articles(
    keyword: str,
    source: str,
    search_url: str,
) -> list[dict]:
    from loguru import logger
    results: list[dict] = []
    seen_urls: set[str] = set()

    cfg = _make_browser_cfg()
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
        async with AsyncWebCrawler(config=cfg) as crawler:
            # ── Search results page ────────────────────────────────────────────
            search_result = await crawler.arun(
                url=search_url,
                config=search_run_cfg(),
            )

            if not getattr(search_result, "success", False):
                # Retry once on failure
                search_result = await crawler.arun(
                    url=search_url,
                    config=search_run_cfg(),
                )

            if not getattr(search_result, "success", False):
                logger.warning(f"[{source}] Search failed for '{keyword}' after retry")
                return results

            html = search_result.html
            article_links = _extract_links(html, source)
            if article_links:
                logger.info(f"[{source}] '{keyword}': found {len(article_links)} links")

            if not article_links:
                return results

            # ── Visit each article ─────────────────────────────────────────────
            for link in article_links[:MAX_ARTICLES_PER_CRAWLER]:
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                art_result = await crawler.arun(url=link, config=article_run_cfg())
                if not getattr(art_result, "success", False):
                    continue

                title = _extract_title(art_result.html, source)
                body = _extract_body(art_result.html, source)

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

def _extract_links(html: str, source: str) -> list[str]:
    """
    Per-site article URL patterns.
    All use numeric article IDs in path to distinguish real articles
    from section/index pages.
    """
    links: list[str] = []
    seen: set[str] = set()

    if source == "detik":
        # Article: https://news.detik.com/<cat>/d-<NUMBER>/<slug>
        pat = r'href="(https?://news\.detik\.com/[^"?]+/d-\d+[^"?]*)"'
        for m in re.findall(pat, html, re.IGNORECASE):
            if m not in seen:
                seen.add(m)
                links.append(m)

    elif source == "kompas":
        # Article: https://www.kompas.com/<section>/<id>/<slug>
        #   e.g. https://www.kompas.com/tren/news/12345/slug
        pat = r'href="(https?://www\.kompas\.com/\w{3,}/[^"?]+"\s*)'
        for raw in re.findall(pat, html, re.IGNORECASE):
            url = raw.rstrip().rstrip('"')
            if "kompas.com/search" in url or url in seen:
                continue
            # must have numeric segment (article ID)
            if re.search(r'/[a-z]{3,}/\d{5,}', url):
                seen.add(url)
                links.append(url)

    elif source == "tribun":
        # Article: https://www.tribunnews.com/news/<ID>/<slug>
        pat = r'href="(https?://www\.tribunnews\.com/news/\d+[^"?]*)"'
        for m in re.findall(pat, html, re.IGNORECASE):
            if m not in seen:
                seen.add(m)
                links.append(m)

    return links


def _extract_title(html: str, source: str) -> str:
    """Extract article <h1> title using source-specific selectors."""
    patterns = {
        "detik": [
            r'<h1[^>]*\bclass="[^"]*\bdetail__title\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
        "kompas": [
            r'<h1[^>]*\bclass="[^"]*\bread__title\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
        "tribun": [
            r'<h1[^>]*\bclass="[^"]*\bf40\b[^"]*"[^>]*>(.*?)</h1>',
            r'<h1[^>]*>(.*?)</h1>',
        ],
    }

    for pat in patterns.get(source, patterns["detik"]):
        m = re.search(pat, html, re.DOTALL)
        if m:
            return _strip_tags(m.group(1))
    return ""


def _extract_body(html: str, source: str) -> str:
    """Extract article body text using source-specific selectors."""
    if source == "detik":
        m = re.search(
            r'<div[^>]*\bclass="[^"]*\bdetail__body-text\b[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL,
        )
        if m:
            return _strip_tags(m.group(1))

    elif source == "kompas":
        m = re.search(
            r'<div[^>]*\bclass="[^"]*\bread__content\b[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL,
        )
        if m:
            return _strip_tags(m.group(1))

    elif source == "tribun":
        m = re.search(
            r'<div[^>]*\bid="article-2"[^>]*>(.*?)</div>',
            html, re.DOTALL,
        )
        if m:
            return _strip_tags(m.group(1))
        # fallback: collect <p> tags
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        if paras:
            return " ".join(_strip_tags(p) for p in paras[:15] if _strip_tags(p))

    return ""


def _strip_tags(text: str) -> str:
    text = re.sub(r'<[^>]+>', " ", text)
    text = re.sub(r'\s+', " ", text)
    return text.strip()
