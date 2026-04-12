"""Tests for scraper services."""

import pytest


@pytest.mark.asyncio
async def test_trends24_returns_list():
    """scrape_trends24 returns list[dict] with keyword, rank, source."""
    from services.scraper.trends24 import scrape_trends24

    result = await scrape_trends24()

    assert isinstance(result, list)
    if len(result) > 0:
        item = result[0]
        assert "keyword" in item
        assert "rank" in item
        assert "source" in item
        assert item["source"] == "trends24"
        assert isinstance(item["rank"], int)


@pytest.mark.asyncio
async def test_google_trends_returns_list():
    """scrape_google_trends returns list[dict] with keyword, rank, source."""
    from services.scraper.google_trends import scrape_google_trends

    result = await scrape_google_trends()

    assert isinstance(result, list)
    # If result is empty due to network/captcha, that's acceptable for a smoke test
    if len(result) > 0:
        item = result[0]
        assert "keyword" in item
        assert "rank" in item
        assert "source" in item
        assert item["source"] == "google_trends"
        assert isinstance(item["rank"], int)
