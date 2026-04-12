"""Tests for expiry service.

The expiry job uses a module-level get_session(). In tests, we test the
expiry logic directly by simulating what run_expiry_job does with a test session.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update

from shared.shared.models import Keyword, Article, KeywordJustification
from shared.shared.constants import (
    KeywordStatus, KeywordSource, ArticleSource,
    EXPIRY_THRESHOLD_HOURS, IRRELEVANT_EXPIRY_HOURS, FAILED_RETRY_MINUTES
)


async def run_expiry_passes(session):
    """Run all three expiry passes against a given session."""
    now = datetime.now(timezone.utc)

    expired_stale = 0
    expired_irrelevant = 0
    retried_failed = 0

    # Pass 1 - Expire stale enriched keywords
    result = await session.execute(
        select(Keyword)
        .where(Keyword.status == KeywordStatus.ENRICHED)
        .with_for_update(skip_locked=True)
    )
    enriched_keywords = result.scalars().all()
    for kw in enriched_keywords:
        # Load articles
        articles_result = await session.execute(
            select(Article).where(Article.keyword_id == kw.id)
        )
        articles = articles_result.scalars().all()
        max_crawled = None
        if articles:
            max_crawled = max(a.crawled_at for a in articles)
        if max_crawled:
            delta = now - max_crawled
            if delta > timedelta(hours=EXPIRY_THRESHOLD_HOURS):
                kw.status = KeywordStatus.EXPIRED
                expired_stale += 1

    # Pass 2 - Expire irrelevant justified keywords
    result = await session.execute(
        select(Keyword)
        .join(KeywordJustification)
        .where(Keyword.status == KeywordStatus.LLM_JUSTIFIED)
        .where(KeywordJustification.is_relevant == False)
        .with_for_update(skip_locked=True)
    )
    irrelevant_keywords = result.scalars().all()
    for kw in irrelevant_keywords:
        delta = now - kw.updated_at
        if delta > timedelta(hours=IRRELEVANT_EXPIRY_HOURS):
            kw.status = KeywordStatus.EXPIRED
            expired_irrelevant += 1

    # Pass 3 - Retry failed keywords
    result = await session.execute(
        select(Keyword)
        .where(Keyword.status == KeywordStatus.FAILED)
        .with_for_update(skip_locked=True)
    )
    failed_keywords = result.scalars().all()
    for kw in failed_keywords:
        delta = now - kw.updated_at
        if delta > timedelta(minutes=FAILED_RETRY_MINUTES):
            kw.status = KeywordStatus.RAW
            kw.failure_reason = None
            retried_failed += 1

    await session.commit()
    return expired_stale, expired_irrelevant, retried_failed


@pytest.mark.asyncio
async def test_pass1_expires_stale_enriched(test_session):
    """Enriched keyword with article crawled_at > EXPIRY_THRESHOLD_HOURS -> expired."""
    now = datetime.now(timezone.utc)

    kw = Keyword(
        keyword="StaleKeyword",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.ENRICHED,
        scraped_at=now - timedelta(hours=EXPIRY_THRESHOLD_HOURS + 1),
        updated_at=now - timedelta(hours=EXPIRY_THRESHOLD_HOURS + 1),
    )
    test_session.add(kw)
    await test_session.flush()

    old_article = Article(
        keyword_id=kw.id,
        source_site=ArticleSource.DETIK,
        url="https://detik.com/stale-test",
        title="Old Article",
        body="Old content",
        crawled_at=now - timedelta(hours=EXPIRY_THRESHOLD_HOURS + 2),
    )
    test_session.add(old_article)
    await test_session.commit()

    await run_expiry_passes(test_session)
    await test_session.refresh(kw)
    assert kw.status == KeywordStatus.EXPIRED


@pytest.mark.asyncio
async def test_pass1_keeps_fresh_enriched(test_session):
    """Enriched keyword with recent crawled_at -> stays enriched."""
    now = datetime.now(timezone.utc)

    kw = Keyword(
        keyword="FreshKeyword",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.ENRICHED,
        scraped_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
    )
    test_session.add(kw)
    await test_session.flush()

    recent_article = Article(
        keyword_id=kw.id,
        source_site=ArticleSource.DETIK,
        url="https://detik.com/fresh-expiry",
        title="Recent Article",
        body="Recent content",
        crawled_at=now - timedelta(hours=1),
    )
    test_session.add(recent_article)
    await test_session.commit()

    await run_expiry_passes(test_session)
    await test_session.refresh(kw)
    assert kw.status == KeywordStatus.ENRICHED


@pytest.mark.asyncio
async def test_pass2_expires_irrelevant(test_session):
    """Old irrelevant llm_justified keyword -> expired."""
    now = datetime.now(timezone.utc)

    kw = Keyword(
        keyword="IrrelevantKeyword",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.LLM_JUSTIFIED,
        scraped_at=now - timedelta(hours=IRRELEVANT_EXPIRY_HOURS + 2),
        updated_at=now - timedelta(hours=IRRELEVANT_EXPIRY_HOURS + 2),
    )
    test_session.add(kw)
    await test_session.flush()

    justification = KeywordJustification(
        keyword_id=kw.id,
        is_relevant=False,
        justification="Not about government",
        llm_model="test/model",
        processed_at=now - timedelta(hours=IRRELEVANT_EXPIRY_HOURS + 2),
    )
    test_session.add(justification)
    await test_session.commit()

    await run_expiry_passes(test_session)
    await test_session.refresh(kw)
    assert kw.status == KeywordStatus.EXPIRED


@pytest.mark.asyncio
async def test_pass3_resets_failed(test_session):
    """Old failed keyword -> raw, failure_reason=NULL."""
    now = datetime.now(timezone.utc)

    kw = Keyword(
        keyword="FailedToReset",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.FAILED,
        failure_reason="Some error",
        scraped_at=now - timedelta(minutes=FAILED_RETRY_MINUTES + 5),
        updated_at=now - timedelta(minutes=FAILED_RETRY_MINUTES + 5),
    )
    test_session.add(kw)
    await test_session.commit()

    await run_expiry_passes(test_session)
    await test_session.refresh(kw)
    assert kw.status == KeywordStatus.RAW
    assert kw.failure_reason is None


@pytest.mark.asyncio
async def test_pass3_keeps_recent_failed(test_session):
    """Recently failed keyword -> not reset yet."""
    now = datetime.now(timezone.utc)

    kw = Keyword(
        keyword="RecentFailed",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.FAILED,
        failure_reason="Recent error",
        scraped_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )
    test_session.add(kw)
    await test_session.commit()

    await run_expiry_passes(test_session)
    await test_session.refresh(kw)
    assert kw.status == KeywordStatus.FAILED
    assert kw.failure_reason == "Recent error"
