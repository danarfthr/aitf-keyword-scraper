import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordJustification, KeywordEnrichment, Article
from services.llm.client import OpenRouterClient
from services.llm.processor import process_keyword


class MockOpenRouterClient(OpenRouterClient):
    async def chat(self, messages: list[dict]) -> str:
        return '{"is_relevant": true, "justification": "Mock justification.", "expanded_keywords": ["A", "B", "C"]}'


async def main():
    async with get_session() as session:
        async with session.begin():
            kw = Keyword(keyword="Test Keyword", source="test", status="news_sampled")
            session.add(kw)

        async with session.begin():
            result = await session.execute(
                select(Keyword).where(Keyword.keyword == "Test Keyword").order_by(Keyword.id.desc()).limit(1)
            )
            kw = result.scalar_one()

            art = Article(
                keyword_id=kw.id,
                source_site="test",
                url=f"http://test.com/{kw.id}",
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

            await process_keyword(kw, list(articles), client, session)

        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            print("Keyword status after processor:", kw.status)

            just_q = await session.execute(select(KeywordJustification).where(KeywordJustification.keyword_id == kw.id))
            justification = just_q.scalars().first()
            if justification:
                print("Justification row found!")
                print("- is_relevant:", justification.is_relevant)
                print("- justification:", justification.justification)
                print("- llm_model:", justification.llm_model)
            else:
                print("No justification row found.")

            enrich_q = await session.execute(select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == kw.id))
            enrichment = enrich_q.scalars().first()
            if enrichment:
                print("Enrichment row found!")
                print("- expanded_keywords:", enrichment.expanded_keywords)
                print("- source_article_ids:", enrichment.source_article_ids)
                print("- llm_model:", enrichment.llm_model)
            else:
                print("No enrichment row found.")


if __name__ == "__main__":
    asyncio.run(main())
