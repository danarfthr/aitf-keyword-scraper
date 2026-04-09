"""
GET /keywords — List all keywords (filter by status, source)
DELETE /keywords/{id} — Delete a keyword
GET /keywords/fresh — List fresh keywords
"""
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
    scraped_at: str
    expand_trigger: Optional[str]
    parent_id: Optional[str]
    ready_for_scraping: bool


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
