import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordEnrichment, Article
from services.llm.client import OpenRouterClient
from services.llm.enricher import enrich_keyword

class MockOpenRouterClientEnricher(OpenRouterClient):
    async def chat(self, messages: list[dict]) -> str:
        return '{"expanded_keywords": ["A", "B", "C"]}'

async def main():
    async with get_session() as session:
        async with session.begin():
            # Create a test keyword and article
            kw = Keyword(keyword="Test Keyword 2", source="test", status="llm_justified")
            session.add(kw)
            
        async with session.begin():
            # Retrieve the keyword to get its ID
            result = await session.execute(select(Keyword).where(Keyword.keyword == "Test Keyword 2").order_by(Keyword.id.desc()).limit(1))
            kw = result.scalar_one()
            
            art = Article(
                keyword_id=kw.id,
                source_site="test",
                url=f"http://test.com/enrich-{kw.id}",
                title="Test Article 2",
                body="Test body 2"
            )
            session.add(art)
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            
            result = await session.execute(select(Article).where(Article.keyword_id == kw.id))
            articles = result.scalars().all()
            
            client = MockOpenRouterClientEnricher()
            client.model = "mock-model"
            
            await enrich_keyword(kw, list(articles), client, session)
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            print("Keyword status after enricher:", kw.status)
            
            result = await session.execute(select(KeywordEnrichment).where(KeywordEnrichment.keyword_id == kw.id))
            enrichment = result.scalars().first()
            if enrichment:
                print("Enrichment row found!")
                print("- expanded_keywords:", enrichment.expanded_keywords)
                print("- source_article_ids:", enrichment.source_article_ids)
                print("- llm_model:", enrichment.llm_model)
            else:
                print("No enrichment row found.")

if __name__ == "__main__":
    asyncio.run(main())
