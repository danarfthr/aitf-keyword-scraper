"""Scraper service — polls ScrapeRun table or runs on schedule."""

import asyncio
import os
import time

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.shared.db import get_session
from shared.shared.models import ScrapeRun
from shared.shared.constants import KeywordStatus
from services.scraper.trends24 import scrape_trends24
from services.scraper.google_trends import scrape_google_trends
from services.scraper.delta import detect_delta

SCRAPER_POLL_INTERVAL_SECONDS = int(os.environ.get("SCRAPER_POLL_INTERVAL_SECONDS", "300"))
SCRAPE_WINDOW_MINUTES = int(os.environ.get("SCRAPE_WINDOW_MINUTES", "120"))


async def run_scrape_cycle(session: AsyncSession, run: ScrapeRun) -> None:
    """Scrape both sources, detect delta, insert new keywords."""
    from loguru import logger as log

    log.info(f"Starting scrape cycle for run_id={run.id}, source={run.source}")
    try:
        all_scraped = []
        if run.source in ["trends24", "all"]:
            t24 = await scrape_trends24()
            all_scraped.extend(t24)
            log.info(f"Trends24 scraped {len(t24)} keywords")
        if run.source in ["google_trends", "all"]:
            gtr = await scrape_google_trends()
            all_scraped.extend(gtr)
            log.info(f"Google Trends scraped {len(gtr)} keywords")

        deltas = await detect_delta(all_scraped, session, SCRAPE_WINDOW_MINUTES)
        log.info(f"Delta detected: {len(deltas)} new keywords")

        for d in deltas:
            from shared.shared.models import Keyword
            kw = Keyword(
                keyword=d["keyword"],
                source=d["source"],
                rank=d.get("rank"),
                status=KeywordStatus.RAW,
            )
            session.add(kw)

        run.status = "done"
        run.finished_at = func.now()
        run.keywords_inserted = len(deltas)
        log.info(f"Scrape cycle complete for run_id={run.id}")
    except Exception as e:
        log.error(f"Scrape cycle failed for run_id={run.id}: {e}")
        run.status = "failed"
        run.finished_at = func.now()


async def poll_once() -> bool:
    """Poll for a pending ScrapeRun and execute it. Returns True if a run was found."""
    async with get_session() as session:
        async with session.begin():
            result = await session.execute(
                select(ScrapeRun)
                .where(ScrapeRun.status == "running")
                .order_by(ScrapeRun.started_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            run = result.scalar_one_or_none()
            if not run:
                return False

            await run_scrape_cycle(session, run)
            await session.commit()
            return True


async def run_scraper():
    logger.info(f"Scraper service started. Poll interval={SCRAPER_POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            found = await poll_once()
            if not found:
                # No pending runs — just wait for next interval
                pass
        except Exception as e:
            logger.error(f"Scraper loop error: {e}")

        # Heartbeat
        try:
            with open("/tmp/scraper_heartbeat.txt", "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass

        await asyncio.sleep(SCRAPER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_scraper())
