"""
runner.py
=========
Orchestrates the full scrape → filter → classify → save pipeline.
"""

import asyncio
import json
from datetime import datetime, timezone

import nest_asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig

from .config import OUTPUT_DIR
from .filters import is_relevant
from .schema import build_item
from .scrapers import GTR_URL, T24_URL, scrape_google_trends, scrape_trends24

nest_asyncio.apply()


def _process_source(
    raw: list[dict],
    source: str,
    url: str,
    label: str,
    scraped_at: str,
) -> tuple[list[dict], int, int]:
    """
    Apply Stage 0 filter + classify all keywords for one source.

    Returns:
        (items, accepted_count, skipped_count)
    """
    items: list[dict] = []
    accepted = skipped = 0
    total = len(raw)
    print(f"\n[{label}] Running Stage 0 filter + classification ({total} raw keywords)…")

    for i, entry in enumerate(raw, 1):
        kw = entry["keyword"]
        ok, reason = is_relevant(kw)
        if not ok:
            print(f"  ✗ ({i:3}/{total}) SKIP [{reason}]  {kw}")
            skipped += 1
            continue
        print(f"  ✓ ({i:3}/{total}) KEEP  {kw}")
        items.append(
            build_item(source=source, rank=entry["rank"], keyword=kw,
                       scraped_at=scraped_at, url=url)
        )
        accepted += 1

    return items, accepted, skipped


async def run() -> None:
    """Full pipeline: scrape → filter → classify → write JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        gtr_raw = await scrape_google_trends(crawler)
        t24_raw = await scrape_trends24(crawler)

    gtr_items, gtr_ok, gtr_skip = _process_source(gtr_raw, "GTR", GTR_URL, "GTR", scraped_at)
    t24_items, t24_ok, t24_skip = _process_source(t24_raw, "T24", T24_URL, "T24", scraped_at)
    all_items = gtr_items + t24_items

    output_path = OUTPUT_DIR / f"merged_trends_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! {len(all_items)} items saved to {output_path}")
    print(f"   GTR  → accepted: {gtr_ok:3}  skipped: {gtr_skip:3}  (of {len(gtr_raw)})")
    print(f"   T24  → accepted: {t24_ok:3}  skipped: {t24_skip:3}  (of {len(t24_raw)})")
