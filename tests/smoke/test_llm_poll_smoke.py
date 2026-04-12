import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select
from shared.shared.db import get_session
from shared.shared.models import Keyword
import services.llm.main
from unittest.mock import AsyncMock

async def main():
    services.llm.main.OpenRouterClient.chat = AsyncMock(return_value='{"is_relevant": true, "justification": "ok"}')
    async with get_session() as session:
        async with session.begin():
            kw = Keyword(keyword="Test Loop Keyword", source="test", status="news_sampled")
            session.add(kw)
            
    # run the loop for a very short time
    services.llm.main.LLM_POLL_INTERVAL_SECONDS = 2
    task = asyncio.create_task(services.llm.main.run_llm_service())
    await asyncio.sleep(5)
    task.cancel()
    
    async with get_session() as session:
        async with session.begin():
            result = await session.execute(select(Keyword).where(Keyword.keyword == "Test Loop Keyword").order_by(Keyword.id.desc()).limit(1))
            kw = result.scalar_one_or_none()
            if kw:
                print("Status after poll loop:", kw.status)

if __name__ == "__main__":
    asyncio.run(main())
