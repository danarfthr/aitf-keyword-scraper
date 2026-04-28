"""Tests for the combined LLM processor (justifier + enricher in one call)."""

import pytest
from unittest.mock import AsyncMock
from sqlalchemy import select

from shared.shared.models import Keyword, KeywordJustification, KeywordEnrichment
from shared.shared.constants import KeywordStatus
from services.llm.processor import process_keyword


class MockOpenRouterClient:
    def __init__(self, response: str):
        self.model = "test/model"
        self._response = response

    async def chat(self, messages):
        return self._response


@pytest.mark.asyncio
async def test_relevant_saves_justification_and_enrichment(test_session, sample_keyword, sample_articles):
    """KeywordJustification + KeywordEnrichment rows created, status becomes enriched."""
    client = MockOpenRouterClient(
        '{"is_relevant": true, "justification": "Berkaitan dengan program pemerintah.", '
        '"expanded_keywords": ["APBN", "anggaran negara", "belanja pemerintah"]}'
    )
    await process_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()

    just_result = await test_session.execute(
        select(KeywordJustification).where(KeywordJustification.keyword_id == sample_keyword.id)
    )
    justification = just_result.scalar_one_or_none()
    assert justification is not None
    assert justification.is_relevant is True
    assert "pemerintah" in justification.justification

    enrich_result = await test_session.execute(
        select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == sample_keyword.id)
    )
    enrichment = enrich_result.scalar_one_or_none()
    assert enrichment is not None
    assert "APBN" in enrichment.expanded_keywords
    assert "anggaran negara" in enrichment.expanded_keywords

    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.ENRICHED


@pytest.mark.asyncio
async def test_not_relevant_saves_justification_only(test_session, sample_keyword, sample_articles):
    """KeywordJustification row created with is_relevant=false, status becomes expired."""
    client = MockOpenRouterClient(
        '{"is_relevant": false, "justification": "Tidak berkaitan dengan pemerintahan."}'
    )
    await process_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()

    just_result = await test_session.execute(
        select(KeywordJustification).where(KeywordJustification.keyword_id == sample_keyword.id)
    )
    justification = just_result.scalar_one_or_none()
    assert justification is not None
    assert justification.is_relevant is False

    enrich_result = await test_session.execute(
        select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == sample_keyword.id)
    )
    enrichment = enrich_result.scalar_one_or_none()
    assert enrichment is None

    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.EXPIRED


@pytest.mark.asyncio
async def test_fallback_expanded_on_parse_error(test_session, sample_keyword, sample_articles):
    """Bad JSON after retry -> expanded = [original keyword], still enriched."""
    client = MockOpenRouterClient("not json at all")
    await process_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()

    enrich_result = await test_session.execute(
        select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == sample_keyword.id)
    )
    enrichment = enrich_result.scalar_one_or_none()
    assert enrichment.expanded_keywords == ["APBN"]

    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.ENRICHED


@pytest.mark.asyncio
async def test_llm_error_sets_failed(test_session, sample_keyword, sample_articles):
    """LLMError causes keyword status to become failed."""
    from services.llm.client import LLMError

    error_client = MockOpenRouterClient("")
    error_client.chat = AsyncMock(side_effect=LLMError("Network error"))

    await process_keyword(sample_keyword, sample_articles, error_client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)

    assert sample_keyword.status == KeywordStatus.FAILED
    assert "LLM permanent failure: processor" in sample_keyword.failure_reason


@pytest.mark.asyncio
async def test_no_expanded_keywords_defaults_to_original(test_session, sample_keyword, sample_articles):
    """is_relevant=true but empty expanded list -> fallback to original keyword."""
    client = MockOpenRouterClient(
        '{"is_relevant": true, "justification": "Berkaitan.", "expanded_keywords": []}'
    )
    await process_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()

    enrich_result = await test_session.execute(
        select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == sample_keyword.id)
    )
    enrichment = enrich_result.scalar_one_or_none()
    assert enrichment.expanded_keywords == ["APBN"]

    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.ENRICHED
