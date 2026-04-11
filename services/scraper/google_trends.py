import asyncio
import random
from typing import Optional

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from loguru import logger

GTR_URL = "https://trends.google.com/trending?geo=ID&category=10"

_SCROLL_JS = """
async () => {
    let previousHeight = 0;
    while (true) {
        window.scrollBy(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 1500));
        let newHeight = document.body.scrollHeight;
        if (newHeight === previousHeight) break;
        previousHeight = newHeight;
        let rows = document.querySelectorAll('tr');
        if (rows.length >= 105) break;
    }
}
"""

_LAST_ETAG: Optional[str] = None
_CACHED_RESULT: list[dict] = []

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

async def scrape_google_trends() -> list[dict]:
    global _LAST_ETAG, _CACHED_RESULT
    
    retries = 3
    delay = 2.0
    
    for attempt in range(1, retries + 1):
        ua = random.choice(UAS)
        headers = {"User-Agent": ua}
        if _LAST_ETAG:
            headers["If-None-Match"] = _LAST_ETAG
            
        logger.info(f"Google Trends attempt {attempt}: URL={GTR_URL}, UA={ua[:30]}..., ETag={_LAST_ETAG}")
        
        try:
            async with AsyncWebCrawler() as crawler:
                run_conf = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    magic=True,
                    delay_before_return_html=2.0,
                    js_code=_SCROLL_JS,
                    wait_for="js:() => document.querySelectorAll('tr').length >= 100",
                )
                
                result = await crawler.arun(url=GTR_URL, config=run_conf)
                
                if getattr(result, "status_code", 200) == 304:
                    logger.info("Google Trends returned 304. Using cached results.")
                    return _CACHED_RESULT
                    
                if not result.success:
                    logger.warning(f"Google Trends crawl failed on attempt {attempt}")
                    if attempt < retries:
                        await asyncio.sleep(delay ** attempt)
                        continue
                    return []

                soup = BeautifulSoup(result.html, "html.parser")
                raw: list[dict] = []
                for row in soup.find_all("tr"):
                    kw_div = row.find("div", class_="mZ3RIc")
                    if kw_div:
                        keyword = kw_div.get_text(strip=True)
                        if keyword:
                            raw.append({"rank": len(raw) + 1, "keyword": keyword, "source": "google_trends"})
                    if len(raw) >= 100:
                        break

                logger.info(f"Google Trends collected {len(raw)} keywords (status=200).")
                
                _LAST_ETAG = getattr(result, "response_headers", {}).get("ETag", "mock-etag-gtr-success")
                _CACHED_RESULT = raw
                return raw
                
        except Exception as e:
            logger.error(f"Google Trends exception on attempt {attempt}: {e}")
            if attempt < retries:
                await asyncio.sleep(delay ** attempt)
            else:
                return []
                
    return []
