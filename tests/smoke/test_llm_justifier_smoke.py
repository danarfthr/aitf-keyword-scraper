import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordJustification, Article
from services.llm.client import OpenRouterClient
from services.llm.justifier import justify_keyword

class MockOpenRouterClient(OpenRouterClient):
    async def chat(self, messages: list[dict]) -> str:
        return '{"is_relevant": true, "justification": "Mock justification."}'

async def main():
    async with get_session() as session:
        async with session.begin():
            # Create a test keyword and article
            kw = Keyword(keyword="Test Keyword", source="test", status="news_sampled")
            session.add(kw)
            
        async with session.begin():
            # Retrieve the keyword to get its ID
            result = await session.execute(select(Keyword).where(Keyword.keyword == "Test Keyword").order_by(Keyword.id.desc()).limit(1))
            kw = result.scalar_one()
            
            art = Article(
                keyword_id=kw.id,
                source_site="test",
                url="http://test.com/1",
                title="Test Article",
                body="Test body"
            )
            session.add(art)
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            
            result = await session.execute(select(Article).where(Article.keyword_id == kw.id))
            articles = result.scalars().all()
            
            client = MockOpenRouterClient()
            client.model = "mock-model"
            
            await justify_keyword(kw, list(articles), client, session)
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            print("Keyword status after justifier:", kw.status)
            
            result = await session.execute(select(KeywordJustification).where(KeywordJustification.keyword_id == kw.id))
            justification = result.scalars().first()
            if justification:
                print("Justification row found!")
                print("- is_relevant:", justification.is_relevant)
                print("- justification:", justification.justification)
                print("- llm_model:", justification.llm_model)
            else:
                print("No justification row found.")

if __name__ == "__main__":
    asyncio.run(main())
