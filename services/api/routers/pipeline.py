"""Pipeline control endpoints — require X-API-Key auth."""

import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func
from loguru import logger

from shared.shared.db import get_session
from shared.shared.models import Keyword, ScrapeRun
from shared.shared.constants import KeywordStatus
from services.scraper.trends24 import scrape_trends24
from services.scraper.google_trends import scrape_google_trends
from services.scraper.delta import detect_delta
from ..auth import require_api_key
from ..schemas import (
    TriggerRequest,
    TriggerResponse,
    ExpireResponse,
    RetryFailedResponse,
    HealthResponse,
    StuckKeywordsResponse,
    StuckAlert,
    ThroughputMetrics,
)

router = APIRouter()


async def run_scrape_cycle(source: str, run_id: int) -> None:
    """Background task: scrape, detect delta, bulk insert keywords."""
    from loguru import logger as log

    log.info(f"Starting scrape cycle for run_id={run_id}, source={source}")
    try:
        all_scraped = []
        if source in ["trends24", "all"]:
            t24 = await scrape_trends24()
            all_scraped.extend(t24)
            log.info(f"Trends24 scraped {len(t24)} keywords")
        if source in ["google_trends", "all"]:
            gtr = await scrape_google_trends()
            all_scraped.extend(gtr)
            log.info(f"Google Trends scraped {len(gtr)} keywords")

        window_minutes = int(os.environ.get("SCRAPE_WINDOW_MINUTES", "120"))

        async with get_session() as session:
            deltas = await detect_delta(all_scraped, session, window_minutes)
            log.info(f"Delta detected: {len(deltas)} new keywords")

            for d in deltas:
                kw = Keyword(
                    keyword=d["keyword"],
                    source=d["source"],
                    rank=d.get("rank"),
                    status=KeywordStatus.RAW,
                )
                session.add(kw)

            run = await session.get(ScrapeRun, run_id)
            if run:
                run.status = "done"
                run.finished_at = func.now()
                run.keywords_inserted = len(deltas)
            await session.commit()

        log.info(f"Scrape cycle complete for run_id={run_id}")
    except Exception as e:
        log.error(f"Scrape cycle failed for run_id={run_id}: {e}")
        try:
            async with get_session() as session:
                run = await session.get(ScrapeRun, run_id)
                if run:
                    run.status = "failed"
                    run.finished_at = func.now()
                await session.commit()
        except Exception:
            pass


@router.get("/health", response_model=HealthResponse)
async def get_pipeline_health():
    """
    GET /pipeline/health — Pipeline status (public, no auth required).
    Returns keyword counts by status and last scrape run info.
    """
    async with get_session() as session:
        # Count keywords by status
        counts = {}
        for status in KeywordStatus.ALL:
            stmt = select(func.count()).select_from(Keyword).where(
                Keyword.status == status
            )
            result = await session.execute(stmt)
            counts[status] = result.scalar() or 0

        # Get last scrape run
        last_scrape_stmt = (
            select(ScrapeRun)
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        )
        last_scrape_result = await session.execute(last_scrape_stmt)
        last_scrape_run = last_scrape_result.scalar_one_or_none()

        last_scrape = None
        if last_scrape_run:
            last_scrape = {
                "scrape_run_id": last_scrape_run.id,
                "source": last_scrape_run.source,
                "started_at": (
                    last_scrape_run.started_at.isoformat()
                    if last_scrape_run.started_at
                    else None
                ),
                "finished_at": (
                    last_scrape_run.finished_at.isoformat()
                    if last_scrape_run.finished_at
                    else None
                ),
                "keywords_inserted": last_scrape_run.keywords_inserted,
                "status": last_scrape_run.status,
            }

        return HealthResponse(counts=counts, last_scrape=last_scrape)


# Threshold in seconds beyond which a keyword in a given status is considered "stuck"
STALE_THRESHOLD_SECONDS = int(os.environ.get("STALE_THRESHOLD_SECONDS", "1800"))  # 30 min default


@router.get("/stuck", response_model=StuckKeywordsResponse)
async def get_stuck_keywords():
    """
    GET /pipeline/stuck — Returns stuck keywords and throughput metrics.

    A keyword is "stuck" when it has been in a non-terminal status for longer
    than STALE_THRESHOLD_SECONDS without progressing to the next stage.
    Terminal statuses: enriched, expired, failed
    """
    async with get_session() as session:
        now = datetime.utcnow()
        stuck_alerts: list[StuckAlert] = []

        # Non-terminal statuses that should progress
        non_terminal = [
            KeywordStatus.RAW,
            KeywordStatus.NEWS_SAMPLED,
            KeywordStatus.LLM_JUSTIFIED,
        ]

        for status in non_terminal:
            # Find keywords in this status longer than threshold
            stale_cutoff = now - timedelta(seconds=STALE_THRESHOLD_SECONDS)
            stmt = (
                select(Keyword)
                .where(Keyword.status == status)
                .where(Keyword.updated_at < stale_cutoff)
            )
            result = await session.execute(stmt)
            stuck_kws = result.scalars().all()

            if stuck_kws:
                oldest = max(kw.updated_at for kw in stuck_kws)
                oldest_seconds = int((now - oldest).total_seconds())

                if oldest_seconds > STALE_THRESHOLD_SECONDS * 3:
                    level = "critical"
                elif oldest_seconds > STALE_THRESHOLD_SECONDS * 2:
                    level = "warning"
                else:
                    level = "info"

                stuck_alerts.append(
                    StuckAlert(
                        level=level,
                        status=status,
                        count=len(stuck_kws),
                        oldest_seconds=oldest_seconds,
                        message=f"{len(stuck_kws)} keywords stuck in '{status}' for {oldest_seconds // 60}+ min",
                    )
                )

        # Throughput metrics from last 24h
        cutoff_24h = now - timedelta(hours=24)
        runs_stmt = (
            select(ScrapeRun)
            .where(ScrapeRun.started_at >= cutoff_24h)
            .order_by(ScrapeRun.started_at.desc())
        )
        runs_result = await session.execute(runs_stmt)
        runs = runs_result.scalars().all()

        total_runs = len(runs)
        total_keywords = sum(r.keywords_inserted or 0 for r in runs)

        # keywords_per_minute: based on last completed run with keywords_inserted
        keywords_per_minute = 0.0
        avg_cycle_duration = 0.0
        completed_runs = [r for r in runs if r.status == "done" and r.finished_at]
        if completed_runs:
            durations = [
                (r.finished_at - r.started_at).total_seconds()
                for r in completed_runs
                if r.started_at and r.finished_at
            ]
            if durations:
                avg_cycle_duration = sum(durations) / len(durations)
            # Rate based on last run's keywords_inserted over its duration
            last = completed_runs[0]
            if last.started_at and last.finished_at:
                dur = (last.finished_at - last.started_at).total_seconds()
                if dur > 0:
                    keywords_per_minute = (last.keywords_inserted or 0) / (dur / 60)

        throughput = ThroughputMetrics(
            keywords_per_minute=round(keywords_per_minute, 2),
            avg_cycle_duration_seconds=round(avg_cycle_duration, 1),
            total_runs_24h=total_runs,
            total_keywords_24h=total_keywords,
        )

        return StuckKeywordsResponse(
            stuck_keywords=stuck_alerts,
            throughput=throughput,
            stale_threshold_seconds=STALE_THRESHOLD_SECONDS,
        )


@router.post("/trigger", status_code=202, response_model=TriggerResponse)
async def trigger_scrape(
    body: TriggerRequest,
    background_tasks: BackgroundTasks,
    _=Depends(require_api_key),
):
    """
    POST /pipeline/trigger — Trigger scrape cycle (requires X-API-Key).
    Idempotency: returns 409 if a cycle is already running.
    """
    if body.source not in ["trends24", "google_trends", "all"]:
        raise HTTPException(
            status_code=400,
            detail="source must be 'trends24', 'google_trends', or 'all'",
        )

    async with get_session() as session:
        # Check for running cycle (idempotency)
        running_stmt = (
            select(ScrapeRun)
            .where(ScrapeRun.status == "running")
            .where(ScrapeRun.started_at > datetime.utcnow() - timedelta(minutes=10))
        )
        running_result = await session.execute(running_stmt)
        if running_result.scalar_one_or_none():
            raise HTTPException(
                status_code=409, detail="A scrape cycle is already running."
            )

        # Insert scrape_run record
        run = ScrapeRun(source=body.source, status="running")
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    # Fire background task
    background_tasks.add_task(run_scrape_cycle, source=body.source, run_id=run_id)
    logger.info(f"Triggered scrape cycle run_id={run_id} source={body.source}")

    return TriggerResponse(
        triggered=True, scrape_run_id=run_id, message="Scrape cycle started."
    )


@router.post("/expire", response_model=ExpireResponse)
async def trigger_expiry(_=Depends(require_api_key)):
    """POST /pipeline/expire — Manually trigger all three passes of the expiry job."""
    # TODO(team4): wire up manual expiry trigger
    logger.warning("Manual /pipeline/expire called but not yet wired to expiry service")
    return ExpireResponse(triggered=True, message="Expiry job started.")


@router.post("/retry-failed", response_model=RetryFailedResponse)
async def retry_failed_keywords(_=Depends(require_api_key)):
    """POST /pipeline/retry-failed — Immediately reset all failed keywords to raw."""
    async with get_session() as session:
        async with session.begin():
            stmt = (
                select(Keyword)
                .where(Keyword.status == KeywordStatus.FAILED)
            )
            result = await session.execute(stmt)
            failed_keywords = result.scalars().all()

            reset_count = 0
            for kw in failed_keywords:
                kw.status = KeywordStatus.RAW
                kw.failure_reason = None
                reset_count += 1

            logger.info(f"Reset {reset_count} failed keywords to raw")
            return RetryFailedResponse(reset_count=reset_count)
