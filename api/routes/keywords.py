"""
GET  /keywords       — List all keywords (filter by status, source)
GET  /keywords/fresh — List fresh keywords
POST /keywords       — Add a manual keyword
DELETE /keywords/{id} — Delete a keyword
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from database import SessionLocal
from models.keyword import Keyword, KeywordStatus, Source

router = APIRouter()


class KeywordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    keyword: str
    source: Source
    rank: int
    status: KeywordStatus
    scraped_at: datetime
    expand_trigger: Optional[str]
    parent_id: Optional[str]
    ready_for_scraping: bool


class ManualKeywordRequest(BaseModel):
    keywords: list[str]


class ManualKeywordResult(BaseModel):
    added: int
    duplicates: int


@router.get("", response_model=list[KeywordResponse])
def list_keywords(
    status: Optional[KeywordStatus] = Query(None),
    source: Optional[Source] = Query(None),
):
    db: Session = SessionLocal()
    try:
        q = db.query(Keyword)
        if status:
            q = q.filter(Keyword.status == status)
        if source:
            q = q.filter(Keyword.source == source)
        return q.order_by(Keyword.rank).all()
    finally:
        db.close()


@router.get("/fresh", response_model=list[KeywordResponse])
def list_fresh_keywords():
    db: Session = SessionLocal()
    try:
        return (
            db.query(Keyword)
            .filter(Keyword.status == KeywordStatus.FRESH)
            .filter(Keyword.ready_for_scraping == True)
            .order_by(Keyword.rank)
            .all()
        )
    finally:
        db.close()


@router.post("", response_model=ManualKeywordResult)
def add_manual_keywords(request: ManualKeywordRequest):
    """Add one or more keywords manually. They are created as FRESH and ready for scraping."""
    db: Session = SessionLocal()
    try:
        added = duplicates = 0
        now = datetime.now(timezone.utc)

        for kw_text in request.keywords:
            kw_text = kw_text.strip()
            if not kw_text:
                continue

            existing = db.query(Keyword).filter(Keyword.keyword == kw_text).first()
            if existing:
                duplicates += 1
                continue

            kw = Keyword(
                keyword=kw_text,
                source=Source.MANUAL,
                rank=0,
                scraped_at=now,
                status=KeywordStatus.FRESH,
                ready_for_scraping=True,
            )
            db.add(kw)
            added += 1

        db.commit()
        return ManualKeywordResult(added=added, duplicates=duplicates)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()


@router.delete("/{keyword_id}")
def delete_keyword(keyword_id: str):
    db: Session = SessionLocal()
    try:
        kw = db.query(Keyword).filter(Keyword.id == keyword_id).first()
        if not kw:
            raise HTTPException(status_code=404, detail="Keyword not found")
        db.delete(kw)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
