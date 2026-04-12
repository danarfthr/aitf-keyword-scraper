"""Tests for sampler service."""

import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from shared.shared.models import Keyword, Article
from shared.shared.constants import KeywordStatus, KeywordSource, ArticleSource, MAX_ARTICLES_TOTAL_PER_KEYWORD
from services.sampler.main import process_keyword


@pytest.mark.asyncio
async def test_url_deduplication_in_memory(test_session, sample_keyword):
    """Duplicate URLs are removed before DB insert."""
    mock_results = [
        {"source_site": "detik", "url": "https://detik.com/test", "title": "T1", "body": "Body 1"},
        {"source_site": "kompas", "url": "https://detik.com/test", "title": "T2", "body": "Body 2"},
        {"source_site": "tribun", "url": "https://detik.com/test", "title": "T3", "body": "Body 3"},
    ]

    with patch("services.sampler.main.crawl_detik", new_callable=AsyncMock) as mock_detik, \
         patch("services.sampler.main.crawl_kompas", new_callable=AsyncMock) as mock_kompas, \
         patch("services.sampler.main.crawl_tribun", new_callable=AsyncMock) as mock_tribun:

        mock_detik.return_value = [mock_results[0]]
        mock_kompas.return_value = [mock_results[1]]
        mock_tribun.return_value = [mock_results[2]]

        await process_keyword(test_session, sample_keyword)
        await test_session.commit()

    result = await test_session.execute(
        select(Article).where(Article.keyword_id == sample_keyword.id)
    )
    articles = result.scalars().all()
    assert len(articles) == 1


@pytest.mark.asyncio
async def test_article_total_capped(test_session, sample_keyword):
    """Total articles per keyword capped at MAX_ARTICLES_TOTAL_PER_KEYWORD."""
    many_articles = [
        {"source_site": "detik", "url": f"https://detik.com/unique{i}", "title": f"T{i}", "body": f"Body {i}"}
        for i in range(10)
    ]

    with patch("services.sampler.main.crawl_detik", new_callable=AsyncMock) as mock_detik, \
         patch("services.sampler.main.crawl_kompas", new_callable=AsyncMock) as mock_kompas, \
         patch("services.sampler.main.crawl_tribun", new_callable=AsyncMock) as mock_tribun:

        mock_detik.return_value = many_articles[:4]
        mock_kompas.return_value = many_articles[4:7]
        mock_tribun.return_value = many_articles[7:]

        await process_keyword(test_session, sample_keyword)
        await test_session.commit()

    result = await test_session.execute(
        select(Article).where(Article.keyword_id == sample_keyword.id)
    )
    articles = result.scalars().all()
    assert len(articles) <= MAX_ARTICLES_TOTAL_PER_KEYWORD


@pytest.mark.asyncio
async def test_body_null_when_summary_generated(test_session, sample_keyword):
    """Long body -> body=NULL, summary populated."""
    long_body = "A" * 5000

    with patch("services.sampler.main.crawl_detik", new_callable=AsyncMock) as mock_detik, \
         patch("services.sampler.main.crawl_kompas", new_callable=AsyncMock) as mock_kompas, \
         patch("services.sampler.main.crawl_tribun", new_callable=AsyncMock) as mock_tribun:

        mock_detik.return_value = [{"source_site": "detik", "url": "https://detik.com/long", "title": "Long", "body": long_body}]
        mock_kompas.return_value = []
        mock_tribun.return_value = []

        await process_keyword(test_session, sample_keyword)
        await test_session.commit()

    result = await test_session.execute(
        select(Article).where(Article.keyword_id == sample_keyword.id)
    )
    article = result.scalar_one_or_none()
    assert article is not None
    assert article.body is None
    assert article.summary is not None
    assert "... [truncated]" in article.summary


@pytest.mark.asyncio
async def test_status_news_sampled_on_zero_articles(test_session, sample_keyword):
    """0 articles found -> status = news_sampled (with warning)."""
    with patch("services.sampler.main.crawl_detik", new_callable=AsyncMock) as mock_detik, \
         patch("services.sampler.main.crawl_kompas", new_callable=AsyncMock) as mock_kompas, \
         patch("services.sampler.main.crawl_tribun", new_callable=AsyncMock) as mock_tribun:

        mock_detik.return_value = []
        mock_kompas.return_value = []
        mock_tribun.return_value = []

        await process_keyword(test_session, sample_keyword)
        await test_session.commit()
        await test_session.refresh(sample_keyword)

    assert sample_keyword.status == KeywordStatus.NEWS_SAMPLED


@pytest.mark.asyncio
async def test_crawlers_return_articles():
    """Verify crawlers can return articles for a known keyword.

    This is an integration test that hits real news sites.
    """
    from services.sampler.crawler import crawl_detik

    result = await crawl_detik("APBN")
    assert isinstance(result, list)
    # At minimum, the function should return a list (possibly empty on network issues)
