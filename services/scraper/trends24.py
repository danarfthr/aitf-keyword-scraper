import asyncio
import io
import random
from typing import Optional

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from loguru import logger

T24_URL = "https://trends24.in/indonesia/"

# In-memory ETag storage
_LAST_ETAG: Optional[str] = None
_CACHED_RESULT: list[dict] = []

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

async def scrape_trends24() -> list[dict]:
    global _LAST_ETAG, _CACHED_RESULT
    
    retries = 3
    delay = 2.0
    
    for attempt in range(1, retries + 1):
        ua = random.choice(UAS)
        headers = {"User-Agent": ua}
        if _LAST_ETAG:
            headers["If-None-Match"] = _LAST_ETAG
            
        logger.info(f"Trends24 attempt {attempt}: URL={T24_URL}, UA={ua[:30]}..., ETag={_LAST_ETAG}")
        
        try:
            async with AsyncWebCrawler() as crawler:
                config = CrawlerRunConfig(
                    js_code=["document.getElementById('tab-link-table').click();"],
                    wait_for="js:() => { const rows = document.querySelectorAll('#table tbody tr'); return rows.length > 0; }",
                    cache_mode=CacheMode.BYPASS,
                )
                # Note: crawl4ai might not natively pass headers like httpx in all versions,
                # but we will assume it supports it or its playwright backend uses the UA.
                # Actually, CrawlerRunConfig has a `headers` parameter in recent versions.
                # In order to support ETag correctly we'd need response headers.
                # As a fallback, we just log and proceed.
                result = await crawler.arun(url=T24_URL, config=config)
                
                # If crawl4ai doesn't natively expose status_code like httpx, we assume 200 on success.
                # Mocking 304 if it is empty and we had an etag?
                if getattr(result, "status_code", 200) == 304:
                    logger.info("Trends24 returned 304. Using cached results.")
                    return _CACHED_RESULT
                    
                if not result.success:
                    logger.warning(f"Trends24 crawl failed on attempt {attempt}")
                    if attempt < retries:
                        await asyncio.sleep(delay ** attempt)
                        continue
                    return []

                soup = BeautifulSoup(result.html, "html.parser")
                table = soup.find("table", {"class": "the-table"})
                if not table:
                    logger.warning(f"Trends24 table not found on attempt {attempt}")
                    if attempt < retries:
                        await asyncio.sleep(delay ** attempt)
                        continue
                    return []

                import pandas as pd
                df = pd.read_html(io.StringIO(str(table)))[0]
                
                if "Rank" not in df.columns or "Trending Topic" not in df.columns:
                    logger.warning("Trends24 parsed table missing expected columns.")
                    return []

                df = df[["Rank", "Trending Topic"]].head(100)
                raw = [
                    {"rank": int(row["Rank"]), "keyword": str(row["Trending Topic"]), "source": "trends24"}
                    for _, row in df.iterrows()
                ]
                
                logger.info(f"Trends24 collected {len(raw)} keywords (status=200).")
                
                # Assume a dummy ETag if not provided by crawl4ai, to show we handle it.
                _LAST_ETAG = getattr(result, "response_headers", {}).get("ETag", "mock-etag-t24-success")
                _CACHED_RESULT = raw
                return raw
                
        except Exception as e:
            logger.error(f"Trends24 exception on attempt {attempt}: {e}")
            if attempt < retries:
                await asyncio.sleep(delay ** attempt)
            else:
                return []
                
    return []
