"""
POST /scrape — Trigger keyword scrape from GTR + T24
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from crawl4ai import AsyncWebCrawler, BrowserConfig
import nest_asyncio
import asyncio

nest_asyncio.apply()

from keyword_scraper.scrapers import scrape_google_trends, scrape_trends24
from database import SessionLocal
from models.keyword import Keyword, Source, KeywordStatus

router = APIRouter()


class ScrapeResult(BaseModel):
    gtr_count: int
    t24_count: int
    total: int
    errors: list[str]


@router.post("", response_model=ScrapeResult)
async def trigger_scrape():
    errors = []
    db: Session = SessionLocal()
    try:
        async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
            gtr_raw = await scrape_google_trends(crawler)
            t24_raw = await scrape_trends24(crawler)

        scraped_at = datetime.now(timezone.utc)
        gtr_count = _upsert_keywords(db, gtr_raw, Source.GTR, scraped_at)
        t24_count = _upsert_keywords(db, t24_raw, Source.T24, scraped_at)
        db.commit()

        return ScrapeResult(gtr_count=gtr_count, t24_count=t24_count, total=gtr_count + t24_count, errors=errors)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()


def _upsert_keywords(db: Session, raw: list[dict], source: Source, scraped_at) -> int:
    """Insert new keywords; update rank/scraped_at for existing RAW/FILTERED."""
    count = 0
    for entry in raw[:100]:
        existing = db.query(Keyword).filter(Keyword.keyword == entry["keyword"]).first()
        if existing:
            if existing.status in (KeywordStatus.RAW, KeywordStatus.FILTERED):
                existing.rank = entry["rank"]
                existing.scraped_at = scraped_at
        else:
            kw = Keyword(
                keyword=entry["keyword"],
                source=source,
                rank=entry["rank"],
                scraped_at=scraped_at,
                status=KeywordStatus.RAW,
            )
            db.add(kw)
            count += 1
    return count
