import asyncio
import os
import time
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordJustification
from shared.shared.constants import KeywordStatus
from .client import OpenRouterClient
from .justifier import justify_keyword
from .enricher import enrich_keyword

LLM_POLL_INTERVAL_SECONDS = int(os.environ.get("LLM_POLL_INTERVAL_SECONDS", "30"))
LLM_BATCH_SIZE = int(os.environ.get("LLM_BATCH_SIZE", "10"))


async def run_llm_justifier():
    """Poll for news_sampled keywords and run justification."""
    logger.info(f"LLM Justifier started. Poll interval={LLM_POLL_INTERVAL_SECONDS}s, batch size={LLM_BATCH_SIZE}")
    client = OpenRouterClient()

    while True:
        try:
            logger.info(f"[LLM:JUSTIFIER] Polling batch | status=news_sampled | batch_size={LLM_BATCH_SIZE}")
            async with get_session() as session:
                async with session.begin():
                    result = await session.execute(
                        select(Keyword)
                        .options(selectinload(Keyword.articles))
                        .where(Keyword.status == KeywordStatus.NEWS_SAMPLED)
                        .order_by(Keyword.updated_at.asc())
                        .limit(LLM_BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                    keywords = result.scalars().all()

                    for kw in keywords:
                        await justify_keyword(kw, list(kw.articles), client, session)
                    logger.info(f"[LLM:JUSTIFIER] Batch complete | processed={len(keywords)}")

            with open("/tmp/llm_heartbeat.txt", "w") as f:
                f.write(str(time.time()))

        except Exception as e:
            logger.error(f"LLM Justifier loop error: {e}")

        await asyncio.sleep(LLM_POLL_INTERVAL_SECONDS)


async def run_llm_enricher():
    """Poll for llm_justified+relevant keywords and run enrichment."""
    logger.info(f"LLM Enricher started. Poll interval={LLM_POLL_INTERVAL_SECONDS}s, batch size={LLM_BATCH_SIZE}")
    client = OpenRouterClient()

    while True:
        try:
            logger.info(f"[LLM:ENRICHER] Polling batch | status=llm_justified+relevant | batch_size={LLM_BATCH_SIZE}")
            async with get_session() as session:
                async with session.begin():
                    result = await session.execute(
                        select(Keyword)
                        .join(KeywordJustification)
                        .options(selectinload(Keyword.articles))
                        .where(Keyword.status == KeywordStatus.LLM_JUSTIFIED)
                        .where(KeywordJustification.is_relevant == True)
                        .order_by(Keyword.updated_at.asc())
                        .limit(LLM_BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                    keywords = result.scalars().all()

                    for kw in keywords:
                        await enrich_keyword(kw, list(kw.articles), client, session)
                    logger.info(f"[LLM:ENRICHER] Batch complete | processed={len(keywords)}")

            with open("/tmp/llm_heartbeat.txt", "w") as f:
                f.write(str(time.time()))

        except Exception as e:
            logger.error(f"LLM Enricher loop error: {e}")

        await asyncio.sleep(LLM_POLL_INTERVAL_SECONDS)


async def run_llm_service():
    """Run both justifier and enricher loops concurrently."""
    logger.info("LLM service started (justifier + enricher)")
    await asyncio.gather(run_llm_justifier(), run_llm_enricher())


if __name__ == "__main__":
    asyncio.run(run_llm_service())
