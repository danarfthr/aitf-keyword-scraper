"""Keyword endpoints — public access, no auth required."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from shared.shared.db import get_session
from shared.shared.models import Keyword, Article, KeywordJustification, KeywordEnrichment
from shared.shared.constants import KeywordStatus, KeywordSource, ARTICLE_SOURCES
from ..schemas import (
    EnrichedKeywordItem,
    EnrichedListResponse,
    KeywordDetailResponse,
    ArticleItem,
    JustificationItem,
    EnrichmentItem,
)

router = APIRouter()


@router.get("/enriched", response_model=EnrichedListResponse)
async def get_enriched_keywords(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """GET /keywords/enriched — Enriched keywords for Team 4."""
    async with get_session() as session:
        # Count total
        count_stmt = select(func.count()).select_from(Keyword).where(
            Keyword.status == KeywordStatus.ENRICHED
        )
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Fetch enriched keywords with their enrichments
        stmt = (
            select(Keyword)
            .where(Keyword.status == KeywordStatus.ENRICHED)
            .order_by(Keyword.scraped_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        keywords = result.scalars().all()

        items = []
        for kw in keywords:
            # Fetch enrichment
            enrich_stmt = select(KeywordEnrichment).where(
                KeywordEnrichment.keyword_id == kw.id
            )
            enrich_result = await session.execute(enrich_stmt)
            enrichment = enrich_result.scalar_one_or_none()

            expanded = enrichment.expanded_keywords if enrichment else []

            items.append(
                EnrichedKeywordItem(
                    id=kw.id,
                    keyword=kw.keyword,
                    source=kw.source,
                    rank=kw.rank,
                    scraped_at=kw.scraped_at.isoformat() if kw.scraped_at else "",
                    expanded_keywords=expanded,
                )
            )

        return EnrichedListResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/{keyword_id}", response_model=KeywordDetailResponse)
async def get_keyword_detail(keyword_id: int):
    """GET /keywords/{id} — Full keyword detail including articles, justification, enrichment."""
    async with get_session() as session:
        kw = await session.get(Keyword, keyword_id)
        if not kw:
            raise HTTPException(status_code=404, detail="Keyword not found")

        # Fetch articles
        articles_stmt = select(Article).where(Article.keyword_id == keyword_id)
        articles_result = await session.execute(articles_stmt)
        articles = articles_result.scalars().all()

        # Fetch justification
        just_stmt = select(KeywordJustification).where(
            KeywordJustification.keyword_id == keyword_id
        )
        just_result = await session.execute(just_stmt)
        justification = just_result.scalar_one_or_none()

        # Fetch enrichment
        enrich_stmt = select(KeywordEnrichment).where(
            KeywordEnrichment.keyword_id == keyword_id
        )
        enrich_result = await session.execute(enrich_stmt)
        enrichment = enrich_result.scalar_one_or_none()

        article_items = [
            ArticleItem(
                id=a.id,
                source_site=a.source_site,
                url=a.url,
                title=a.title,
                crawled_at=a.crawled_at.isoformat() if a.crawled_at else "",
            )
            for a in articles
        ]

        just_item = None
        if justification:
            just_item = JustificationItem(
                is_relevant=justification.is_relevant,
                justification=justification.justification,
                llm_model=justification.llm_model,
                processed_at=justification.processed_at.isoformat()
                if justification.processed_at
                else "",
            )

        enrich_item = None
        if enrichment:
            enrich_item = EnrichmentItem(
                expanded_keywords=enrichment.expanded_keywords,
                llm_model=enrichment.llm_model,
                processed_at=enrichment.processed_at.isoformat()
                if enrichment.processed_at
                else "",
            )

        return KeywordDetailResponse(
            id=kw.id,
            keyword=kw.keyword,
            source=kw.source,
            rank=kw.rank,
            status=kw.status,
            failure_reason=kw.failure_reason,
            scraped_at=kw.scraped_at.isoformat() if kw.scraped_at else "",
            updated_at=kw.updated_at.isoformat() if kw.updated_at else "",
            articles=article_items,
            justification=just_item,
            enrichment=enrich_item,
        )


@router.get("/status/{status}", response_model=EnrichedListResponse)
async def get_keywords_by_status(
    status: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    since: Optional[str] = Query(default=None, description="ISO timestamp — only keywords scraped after this time"),
    source: Optional[str] = Query(default=None, description="Filter by source: trends24 or google_trends"),
    include_relevant: bool = Query(default=False, description="Join justification table to include is_relevant field"),
):
    """GET /keywords/status/{status} — Paginated, filterable by status."""
    if status not in KeywordStatus.ALL:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {KeywordStatus.ALL}",
        )

    async with get_session() as session:
        # Build base filter
        conditions = [Keyword.status == status]

        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                conditions.append(Keyword.scraped_at >= since_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid since timestamp format")

        if source:
            if source not in KeywordSource.ALL:
                raise HTTPException(status_code=400, detail="source must be trends24 or google_trends")
            conditions.append(Keyword.source == source)

        count_stmt = select(func.count()).select_from(Keyword).where(*conditions)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = (
            select(Keyword)
            .where(*conditions)
            .order_by(Keyword.scraped_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        keywords = result.scalars().all()

        items = []
        for kw in keywords:
            if include_relevant and status == KeywordStatus.LLM_JUSTIFIED:
                just_stmt = select(KeywordJustification).where(
                    KeywordJustification.keyword_id == kw.id
                )
                just_result = await session.execute(just_stmt)
                justification = just_result.scalar_one_or_none()
                is_rel = justification.is_relevant if justification else None
                items.append(
                    EnrichedKeywordItem(
                        id=kw.id,
                        keyword=kw.keyword,
                        source=kw.source,
                        rank=kw.rank,
                        scraped_at=kw.scraped_at.isoformat() if kw.scraped_at else "",
                        expanded_keywords=[],
                        is_relevant=is_rel,
                    )
                )
            else:
                items.append(
                    EnrichedKeywordItem(
                        id=kw.id,
                        keyword=kw.keyword,
                        source=kw.source,
                        rank=kw.rank,
                        scraped_at=kw.scraped_at.isoformat() if kw.scraped_at else "",
                        expanded_keywords=[],
                    )
                )

        return EnrichedListResponse(total=total, limit=limit, offset=offset, items=items)
