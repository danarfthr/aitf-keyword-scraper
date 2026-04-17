"""Tests for LLM justifier."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select

from shared.shared.models import Keyword, KeywordJustification
from shared.shared.constants import KeywordStatus
from services.llm.justifier import justify_keyword


class MockOpenRouterClient:
    def __init__(self, response: str):
        self.model = "test/model"
        self._response = response

    async def chat(self, messages):
        return self._response


@pytest.mark.asyncio
async def test_saves_justification_row(test_session, sample_keyword, sample_articles):
    """KeywordJustification row is created after justification."""
    client = MockOpenRouterClient('{"is_relevant": true, "justification": "Pemerintah terkait."}')
    await justify_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()

    result = await test_session.execute(
        select(KeywordJustification).where(KeywordJustification.keyword_id == sample_keyword.id)
    )
    justification = result.scalar_one_or_none()
    assert justification is not None
    assert justification.is_relevant is True
    assert "Pemerintah" in justification.justification


@pytest.mark.asyncio
async def test_status_becomes_llm_justified(test_session, sample_keyword, sample_articles):
    """Keyword status changes to llm_justified after call."""
    client = MockOpenRouterClient('{"is_relevant": true, "justification": "Pemerintah terkait."}')
    await justify_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.LLM_JUSTIFIED


@pytest.mark.asyncio
async def test_parse_error_fallback(test_session, sample_keyword, sample_articles):
    """Bad JSON -> retries once -> is_relevant=False, no exception raised."""
    client = MockOpenRouterClient("not json at all")
    await justify_keyword(sample_keyword, sample_articles, client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)
    assert sample_keyword.status == KeywordStatus.LLM_JUSTIFIED

    result = await test_session.execute(
        select(KeywordJustification).where(KeywordJustification.keyword_id == sample_keyword.id)
    )
    justification = result.scalar_one_or_none()
    assert justification.is_relevant is False


@pytest.mark.asyncio
async def test_llm_error_sets_failed(test_session, sample_keyword, sample_articles):
    """LLMError causes keyword status to become failed with reason."""
    from services.llm.client import LLMError

    error_client = MockOpenRouterClient("")
    error_client.chat = AsyncMock(side_effect=LLMError("Network error"))

    await justify_keyword(sample_keyword, sample_articles, error_client, test_session)
    await test_session.commit()
    await test_session.refresh(sample_keyword)

    assert sample_keyword.status == KeywordStatus.FAILED
    assert "LLM permanent failure: justifier" in sample_keyword.failure_reason
