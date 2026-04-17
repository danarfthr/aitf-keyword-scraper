import asyncio
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
import os
from dotenv import load_dotenv
load_dotenv()

from shared.shared.db import get_session
from shared.shared.models import Keyword, Article
from services.sampler.main import process_keyword

async def main():
    async with get_session() as session:
        async with session.begin():
            kw = Keyword(keyword="Jokowi", source="trends24", status="raw")
            session.add(kw)
        
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.keyword == "Jokowi").order_by(Keyword.id.desc()).limit(1))
            kw = result.scalar_one()
            await process_keyword(session, kw)
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            print("Status after sampler:", kw.status)
            
            result = await session.execute(select(Article).where(Article.keyword_id == kw.id))
            articles = result.scalars().all()
            print("Articles fetched:", len(articles))
            if articles:
                print("First article title:", articles[0].title)

if __name__ == "__main__":
    asyncio.run(main())
