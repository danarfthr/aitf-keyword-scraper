"""
schema.py
=========
Builds schema-compliant ScrapedItem dicts from raw scraper output.
"""

import uuid

from .classifier import classify_keyword
from .config import URL_GEO


def build_item(
    source: str,        # "GTR" or "T24"
    rank: int,
    keyword: str,
    scraped_at: str,
    url: str | None,
) -> dict:
    """Return a schema-compliant ScrapedItem dict for a single keyword."""
    labels = classify_keyword(keyword)
    return {
        "id": str(uuid.uuid4()),
        "source_platform": source,
        "keyword": keyword,
        "url": url,
        "scraped_at": scraped_at,
        "trend_date": scraped_at[:10],      # YYYY-MM-DD
        "rank": rank,
        "search_volume": None,
        "volume_label": None,
        "related_queries": None,
        "geo": {"country": URL_GEO, "region": None},
        "kategori_utama": labels["kategori_utama"],
        "sub_kategori": labels["sub_kategori"],
        "sentimen": labels["sentimen"],
        "prioritas": labels["prioritas"],
        "is_auto_labeled": labels["is_auto_labeled"],
        "confidence_score": labels["confidence_score"],
        "ews_flag": False,
        "ews_reason": None,
        "raw_payload": None,
        "created_at": scraped_at,
        "updated_at": None,
    }
