import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from shared.shared.db import get_session
from shared.shared.models import Keyword, Article
import services.expiry.main

async def main():
    async with get_session() as session:
        async with session.begin():
            kw = Keyword(keyword="Test Expiry", source="test", status="enriched")
            session.add(kw)
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.keyword == "Test Expiry").order_by(Keyword.id.desc()).limit(1))
            kw = result.scalar_one()
            
            art = Article(
                keyword_id=kw.id,
                source_site="test",
                url=f"http://test.com/expire-{kw.id}",
                title="Test Expire Article",
                body="Test body",
                crawled_at=datetime.now(timezone.utc) - timedelta(hours=7)
            )
            session.add(art)
            
        await services.expiry.main.run_expiry_job()
            
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.id == kw.id))
            kw = result.scalar_one()
            print("Keyword status after expiry job:", kw.status)

if __name__ == "__main__":
    asyncio.run(main())
