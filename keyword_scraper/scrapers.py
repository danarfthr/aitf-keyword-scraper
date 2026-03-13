"""
scrapers.py
===========
Async scrapers for Google Trends and Trends24 Indonesia.
"""

import io

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

# ---------------------------------------------------------------------------
# Google Trends
# ---------------------------------------------------------------------------

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

GTR_URL = "https://trends.google.com/trending?geo=ID&category=10"


async def scrape_google_trends(crawler: AsyncWebCrawler) -> list[dict]:
    """Scrape up to 100 trending keywords from Google Trends Indonesia."""
    print("\n[GTR] Starting Google Trends scrape…")
    run_conf = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        magic=True,
        delay_before_return_html=2.0,
        js_code=_SCROLL_JS,
        wait_for="js:() => document.querySelectorAll('tr').length >= 100",
    )
    result = await crawler.arun(url=GTR_URL, config=run_conf)
    if not result.success:
        print("[GTR] ERROR: Failed to crawl Google Trends page.")
        return []

    soup = BeautifulSoup(result.html, "html.parser")
    raw: list[dict] = []
    for row in soup.find_all("tr"):
        kw_div = row.find("div", class_="mZ3RIc")
        if kw_div:
            keyword = kw_div.get_text(strip=True)
            if keyword:
                raw.append({"rank": len(raw) + 1, "keyword": keyword})
        if len(raw) >= 100:
            break

    print(f"[GTR] Collected {len(raw)} keywords.")
    return raw


# ---------------------------------------------------------------------------
# Trends24
# ---------------------------------------------------------------------------

T24_URL = "https://trends24.in/indonesia/"


async def scrape_trends24(crawler: AsyncWebCrawler) -> list[dict]:
    """Scrape up to 100 trending keywords from Trends24 Indonesia."""
    print("\n[T24] Starting Trends24 scrape…")
    config = CrawlerRunConfig(
        js_code=["document.getElementById('tab-link-table').click();"],
        wait_for="js:() => { const rows = document.querySelectorAll('#table tbody tr'); return rows.length > 0; }",
    )
    result = await crawler.arun(url=T24_URL, config=config)
    if not result.success:
        print("[T24] ERROR: Failed to crawl Trends24 page.")
        return []

    soup = BeautifulSoup(result.html, "html.parser")
    table = soup.find("table", {"class": "the-table"})
    if not table:
        print("[T24] ERROR: Could not find .the-table element.")
        return []

    try:
        import pandas as pd
        df = pd.read_html(io.StringIO(str(table)))[0]
    except Exception as exc:
        print(f"[T24] ERROR parsing table: {exc}")
        return []

    if "Rank" not in df.columns or "Trending Topic" not in df.columns:
        print(f"[T24] ERROR unexpected columns: {df.columns.tolist()}")
        return []

    df = df[["Rank", "Trending Topic"]].head(100)
    raw = [
        {"rank": int(row["Rank"]), "keyword": str(row["Trending Topic"])}
        for _, row in df.iterrows()
    ]
    print(f"[T24] Collected {len(raw)} keywords.")
    return raw
