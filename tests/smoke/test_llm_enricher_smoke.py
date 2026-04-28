import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordJustification, Article
from services.llm.client import OpenRouterClient
from services.llm.processor import process_keyword


class MockOpenRouterClientNotRelevant(OpenRouterClient):
    async def chat(self, messages: list[dict]) -> str:
        return '{"is_relevant": false, "justification": "Tidak berkaitan dengan pemerintahan."}'


async def main():
    async with get_session() as session:
        async with session.begin():
            kw = Keyword(keyword="Test Keyword 2", source="test", status="news_sampled")
            session.add(kw)

        async with session.begin():
            result = await session.execute(
                select(Keyword).where(Keyword.keyword == "Test Keyword 2").order_by(Keyword.id.desc()).limit(1)
            )
            kw = result.scalar_one()

            art = Article(
                keyword_id=kw.id,
                source_site="test",
                url=f"http://test.com/{kw.id}",
                title="Test Article 2",
                body="Test body 2"
            )
            session.add(art)

        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()

            result = await session.execute(select(Article).where(Article.keyword_id == kw.id))
            articles = result.scalars().all()

            client = MockOpenRouterClientNotRelevant()
            client.model = "mock-model"

            await process_keyword(kw, list(articles), client, session)

        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            print("Keyword status after processor (not relevant):", kw.status)

            just_q = await session.execute(select(KeywordJustification).where(KeywordJustification.keyword_id == kw.id))
            justification = just_q.scalars().first()
            if justification:
                print("Justification row found!")
                print("- is_relevant:", justification.is_relevant)
                print("- justification:", justification.justification)
                print("- llm_model:", justification.llm_model)
            else:
                print("No justification row found.")


if __name__ == "__main__":
    asyncio.run(main())
