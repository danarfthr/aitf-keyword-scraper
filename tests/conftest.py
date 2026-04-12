"""Pytest fixtures for keyword manager tests."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test database URL before importing shared.db
_test_db_url = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://aitf:change_me_in_production@localhost:5432/aitf_test",
)
os.environ["DATABASE_URL"] = _test_db_url

from shared.shared.models import Base, Keyword, Article, KeywordJustification, KeywordEnrichment
from shared.shared.constants import KeywordStatus, KeywordSource, ArticleSource


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    """Create a test engine pointing to a dedicated test database."""
    engine = create_async_engine(_test_db_url, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Isolated AsyncSession for each test.
    Uses autobegin semantics - commits are explicit, rollback on close.
    """
    async_session_maker = async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with async_session_maker() as session:
        yield session
        # Any uncommitted changes roll back on session close


@pytest_asyncio.fixture
async def sample_keyword(test_session: AsyncSession) -> Keyword:
    """Keyword ORM object with status=raw, committed to DB."""
    keyword = Keyword(
        keyword="APBN",
        source=KeywordSource.TRENDS24,
        rank=1,
        status=KeywordStatus.RAW,
        scraped_at=datetime.now(timezone.utc),
    )
    test_session.add(keyword)
    await test_session.commit()
    await test_session.refresh(keyword)
    return keyword


@pytest_asyncio.fixture
async def sample_articles(test_session: AsyncSession, sample_keyword: Keyword) -> list[Article]:
    """3 Article ORM objects linked to sample_keyword."""
    articles = [
        Article(
            keyword_id=sample_keyword.id,
            source_site=ArticleSource.DETIK,
            url="https://detik.com/test1",
            title="Test Article 1",
            body="Ini adalah artikel tentang APBN dan pengelolaan anggaran negara.",
            crawled_at=datetime.now(timezone.utc),
        ),
        Article(
            keyword_id=sample_keyword.id,
            source_site=ArticleSource.KOMPAS,
            url="https://kompas.com/test2",
            title="Test Article 2",
            body="Artikel kedua tentang APBN.",
            crawled_at=datetime.now(timezone.utc),
        ),
        Article(
            keyword_id=sample_keyword.id,
            source_site=ArticleSource.TRIBUN,
            url="https://tribun.com/test3",
            title="Test Article 3",
            body="Artikel ketiga membahas APBN dan belanja negara.",
            crawled_at=datetime.now(timezone.utc),
        ),
    ]
    for art in articles:
        test_session.add(art)
    await test_session.commit()
    for art in articles:
        await test_session.refresh(art)
    return articles


class MockOpenRouterClient:
    """Mock LLM client that returns valid JSON without network calls."""

    def __init__(self, response: str | None = None):
        self.model = "anthropic/claude-3-haiku"
        self._response = response

    async def chat(self, messages: list[dict]) -> str:
        if self._response:
            return self._response
        return '{"is_relevant": true, "justification": "Artikel membahas APBN."}'


@pytest.fixture
def mock_llm_client():
    """Returns a MockOpenRouterClient instance."""
    return MockOpenRouterClient
