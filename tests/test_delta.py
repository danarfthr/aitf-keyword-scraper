"""Tests for scraper delta detection."""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from shared.shared.models import Keyword
from shared.shared.constants import KeywordStatus, KeywordSource
from services.scraper.delta import detect_delta


@pytest.mark.asyncio
async def test_delta_excludes_existing(test_session, sample_keyword):
    """Keyword already in DB window is excluded from delta."""
    scraped = [
        {"keyword": "APBN", "rank": 1, "source": "trends24"},
        {"keyword": "新车", "rank": 2, "source": "trends24"},  # new
    ]
    result = await detect_delta(scraped, test_session, window_minutes=120)
    assert "APBN" not in [kw["keyword"] for kw in result]
    assert "新车" in [kw["keyword"] for kw in result]


@pytest.mark.asyncio
async def test_delta_case_insensitive(test_session):
    """'APBN' and 'apbn' are treated as the same keyword."""
    # Insert lowercase version
    kw = Keyword(
        keyword="apbn",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.RAW,
        scraped_at=datetime.utcnow(),
    )
    test_session.add(kw)
    await test_session.commit()

    scraped = [{"keyword": "APBN", "rank": 1, "source": "trends24"}]
    result = await detect_delta(scraped, test_session, window_minutes=120)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_delta_cross_source(test_session):
    """Same text from different source is NOT a delta if already seen."""
    kw = Keyword(
        keyword="APBN",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.RAW,
        scraped_at=datetime.utcnow(),
    )
    test_session.add(kw)
    await test_session.commit()

    scraped = [
        {"keyword": "APBN", "rank": 5, "source": "google_trends"},  # same text, different source
    ]
    result = await detect_delta(scraped, test_session, window_minutes=120)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_delta_passes_new_keyword(test_session):
    """Keyword not in window is included in delta."""
    scraped = [
        {"keyword": "新车", "rank": 1, "source": "trends24"},
        {"keyword": "NewTopic", "rank": 2, "source": "google_trends"},
    ]
    result = await detect_delta(scraped, test_session, window_minutes=120)
    assert len(result) == 2
    keywords = [kw["keyword"] for kw in result]
    assert "新车" in keywords
    assert "NewTopic" in keywords
