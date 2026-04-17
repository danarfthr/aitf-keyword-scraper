import os
import time
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from shared.shared.db import get_session
from shared.shared.models import Keyword, Article, ScrapeRun
from shared.shared.constants import KeywordStatus
from .models import PostKeywordsRequest, PostScrapeRequest
from services.scraper.trends24 import scrape_trends24
from services.scraper.google_trends import scrape_google_trends
from services.scraper.delta import detect_delta

router = APIRouter()

async def manual_scrape_job(run_id: int, source: str):
    logger.info(f"Starting scrape job for run_id {run_id}, source {source}")
    try:
        all_scraped = []
        if source in ["trends24", "all"]:
            t24 = await scrape_trends24()
            all_scraped.extend(t24)
        if source in ["google_trends", "all"]:
            gtr = await scrape_google_trends()
            all_scraped.extend(gtr)
            
        async with get_session() as session:
            window_minutes = int(os.environ.get("SCRAPE_WINDOW_MINUTES", "120"))
            deltas = await detect_delta(all_scraped, session, window_minutes)
            
            async with session.begin():
                for d in deltas:
                    kw = Keyword(keyword=d["keyword"], source=d["source"], rank=d.get("rank"), status=KeywordStatus.RAW)
                    session.add(kw)
                    
                run = await session.get(ScrapeRun, run_id)
                if run:
                    run.status = "done"
                    run.finished_at = func.now()
                    run.keywords_inserted = len(deltas)
            
    except Exception as e:
        logger.error(f"Scrape job error for run_id {run_id}: {e}")
        async with get_session() as session:
            async with session.begin():
                run = await session.get(ScrapeRun, run_id)
                if run:
                    run.status = "failed"
                    run.finished_at = func.now()

@router.get("/keywords")
async def get_keywords(
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    async with get_session() as session:
        stmt = select(Keyword).order_by(Keyword.scraped_at.desc())
        if status:
            stmt = stmt.where(Keyword.status == status)
        if source:
            stmt = stmt.where(Keyword.source == source)
            
        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        keywords = result.scalars().all()
        
        resp = []
        for kw in keywords:
            resp.append({
                "id": kw.id,
                "keyword": kw.keyword,
                "source": kw.source,
                "rank": kw.rank,
                "status": kw.status,
                "scraped_at": kw.scraped_at.isoformat() if kw.scraped_at else None,
                "updated_at": kw.updated_at.isoformat() if kw.updated_at else None,
                "failure_reason": kw.failure_reason
            })
        return resp

@router.get("/articles")
async def get_articles(keyword_id: int):
    async with get_session() as session:
        stmt = select(Article).where(Article.keyword_id == keyword_id)
        result = await session.execute(stmt)
        articles = result.scalars().all()
        
        return [
            {
                "id": a.id,
                "source_site": a.source_site,
                "url": a.url,
                "title": a.title,
                "summary": a.summary,
                "crawled_at": a.crawled_at.isoformat() if a.crawled_at else None
            }
            for a in articles
        ]

@router.post("/keywords", status_code=201)
async def post_keywords(req: PostKeywordsRequest):
    async with get_session() as session:
        async with session.begin():
            for k in req.keywords:
                kw = Keyword(keyword=k.keyword, source=k.source, status=KeywordStatus.RAW)
                session.add(kw)
    return {"status": "ok"}

@router.post("/scrape")
async def post_scrape(req: PostScrapeRequest, background_tasks: BackgroundTasks):
    if req.source not in ["trends24", "google_trends", "all"]:
        raise HTTPException(status_code=400, detail="Invalid source")
        
    async with get_session() as session:
        async with session.begin():
            run = ScrapeRun(source=req.source, status="running")
            session.add(run)
            await session.flush()
            run_id = run.id
            
    background_tasks.add_task(manual_scrape_job, run_id, req.source)
    return {"run_id": run_id}

@router.get("/system/health")
async def process_health():
    async with get_session() as session:
        try:
            await session.execute(select(1))
            db_status = "ok"
        except Exception:
            db_status = "error"
            
    def check_heartbeat(path):
        try:
            mtime = os.path.getmtime(path)
            if time.time() - mtime < 300:
                return "ok"
            return "stale"
        except Exception:
            return "missing"
            
    return {
        "db": db_status,
        "sampler": check_heartbeat("/tmp/sampler_heartbeat.txt"),
        "llm": check_heartbeat("/tmp/llm_heartbeat.txt"),
        "expiry": check_heartbeat("/tmp/expiry_heartbeat.txt")
    }
