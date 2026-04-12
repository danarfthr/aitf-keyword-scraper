"""Tests for LLM enricher."""

import pytest
from unittest.mock import AsyncMock

from sqlalchemy import select

from shared.shared.models import Keyword, KeywordEnrichment
from shared.shared.constants import KeywordStatus
from services.llm.enricher import enrich_keyword


class MockOpenRouterClient:
    def __init__(self, response: str):
        self.model = "test/model"
        self._response = response

    async def chat(self, messages):
        return self._response


@pytest.mark.asyncio
async def test_saves_enrichment_row(test_session, sample_keyword, sample_articles):
    """KeywordEnrichment row is created after enrichment."""
    sample_keyword.status = KeywordStatus.LLM_JUSTIFIED
    await test_session.commit()

    client = MockOpenRouterClient(
        '{"expanded_keywords": ["APBN", "anggaran negara", "belanja pemerintah"]}'
    )
    await enrich_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()

    result = await test_session.execute(
        select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == sample_keyword.id)
    )
    enrichment = result.scalar_one_or_none()
    assert enrichment is not None
    assert "APBN" in enrichment.expanded_keywords
    assert "anggaran negara" in enrichment.expanded_keywords


@pytest.mark.asyncio
async def test_status_becomes_enriched(test_session, sample_keyword, sample_articles):
    """Keyword status changes to enriched after successful enrichment."""
    sample_keyword.status = KeywordStatus.LLM_JUSTIFIED
    await test_session.commit()

    client = MockOpenRouterClient(
        '{"expanded_keywords": ["APBN", "anggaran negara"]}'
    )
    await enrich_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.ENRICHED


@pytest.mark.asyncio
async def test_fallback_on_parse_error(test_session, sample_keyword, sample_articles):
    """Bad JSON after retry -> expanded = [original keyword]."""
    sample_keyword.status = KeywordStatus.LLM_JUSTIFIED
    await test_session.commit()

    client = MockOpenRouterClient("not json at all")
    await enrich_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)

    result = await test_session.execute(
        select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == sample_keyword.id)
    )
    enrichment = result.scalar_one_or_none()
    assert enrichment.expanded_keywords == ["APBN"]


@pytest.mark.asyncio
async def test_llm_error_sets_failed(test_session, sample_keyword, sample_articles):
    """LLMError causes keyword status to become failed with enricher reason."""
    from services.llm.client import LLMError

    sample_keyword.status = KeywordStatus.LLM_JUSTIFIED
    await test_session.commit()

    error_client = MockOpenRouterClient("")
    error_client.chat = AsyncMock(side_effect=LLMError("Network error"))

    await enrich_keyword(sample_keyword, sample_articles, error_client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)

    assert sample_keyword.status == KeywordStatus.FAILED
    assert "LLM permanent failure: enricher" in sample_keyword.failure_reason
