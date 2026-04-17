import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from shared.shared.db import get_session
from shared.shared.models import Keyword, Article, KeywordJustification
from shared.shared.constants import (
    KeywordStatus,
    EXPIRY_THRESHOLD_HOURS,
    IRRELEVANT_EXPIRY_HOURS,
    FAILED_RETRY_MINUTES,
)

EXPIRY_CHECK_INTERVAL_MINUTES = int(os.environ.get("EXPIRY_CHECK_INTERVAL_MINUTES", "30"))

async def run_expiry_job():
    logger.info("Starting expiry job...")
    now = datetime.now(timezone.utc)
    
    expired_stale = 0
    expired_irrelevant = 0
    retried_failed = 0
    
    try:
        async with get_session() as session:
            # Pass 1 - Expire stale enriched keywords
            async with session.begin():
                result = await session.execute(
                    select(Keyword)
                    .options(selectinload(Keyword.articles))
                    .where(Keyword.status == KeywordStatus.ENRICHED)
                    .with_for_update(skip_locked=True)
                )
                enriched_keywords = result.scalars().all()
                
                for kw in enriched_keywords:
                    max_crawled = None
                    if kw.articles:
                        max_crawled = max(a.crawled_at for a in kw.articles)
                    
                    if max_crawled:
                        delta = now - max_crawled
                        if delta > timedelta(hours=EXPIRY_THRESHOLD_HOURS):
                            kw.status = KeywordStatus.EXPIRED
                            expired_stale += 1

            # Pass 2 - Expire irrelevant justified keywords
            async with session.begin():
                result = await session.execute(
                    select(Keyword)
                    .join(KeywordJustification)
                    .where(Keyword.status == KeywordStatus.LLM_JUSTIFIED)
                    .where(KeywordJustification.is_relevant == False)
                    .with_for_update(skip_locked=True)
                )
                irrelevant_keywords = result.scalars().all()
                for kw in irrelevant_keywords:
                    delta = now - kw.updated_at
                    if delta > timedelta(hours=IRRELEVANT_EXPIRY_HOURS):
                        kw.status = KeywordStatus.EXPIRED
                        expired_irrelevant += 1

            # Pass 3 - Retry failed keywords
            async with session.begin():
                result = await session.execute(
                    select(Keyword)
                    .where(Keyword.status == KeywordStatus.FAILED)
                    .with_for_update(skip_locked=True)
                )
                failed_keywords = result.scalars().all()
                for kw in failed_keywords:
                    delta = now - kw.updated_at
                    if delta > timedelta(minutes=FAILED_RETRY_MINUTES):
                        kw.status = KeywordStatus.RAW
                        kw.failure_reason = None
                        retried_failed += 1

        logger.info(f"Expiry job complete. Expired stale: {expired_stale}, expired irrelevant: {expired_irrelevant}, retried failed: {retried_failed}")
        
    except Exception as e:
        logger.error(f"Error in expiry job: {e}")
        
    # Heartbeat
    try:
        with open("/tmp/expiry_heartbeat.txt", "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


async def main_async():
    logger.info(f"Expiry service started. Check interval: {EXPIRY_CHECK_INTERVAL_MINUTES} minutes")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_expiry_job, 'interval', minutes=EXPIRY_CHECK_INTERVAL_MINUTES, next_run_time=datetime.now())
    scheduler.start()
    
    try:
        # Keep running until cancelled
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        scheduler.shutdown(wait=False)

if __name__ == "__main__":
    asyncio.run(main_async())
