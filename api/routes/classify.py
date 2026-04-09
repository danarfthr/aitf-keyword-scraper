"""
POST /keywords/classify — Apply OpenRouter AI binary filter.
Non-relevant keywords are marked REJECTED (not deleted).
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import SessionLocal
from models.keyword import Keyword, KeywordStatus
from services.openrouter import classify_batch, DEFAULT_MODEL

router = APIRouter()


class ClassifyRequest(BaseModel):
    keyword_ids: list[str]
    model: str = DEFAULT_MODEL


class ClassifyResult(BaseModel):
    total: int
    fresh: int
    rejected: int


@router.post("/classify", response_model=ClassifyResult)
def classify_keywords(request: ClassifyRequest):
    db: Session = SessionLocal()
    try:
        keywords = db.query(Keyword).filter(Keyword.id.in_(request.keyword_ids)).all()
        if not keywords:
            raise HTTPException(status_code=404, detail="No keywords found for the given IDs")

        keyword_texts = [kw.keyword for kw in keywords]
        results = classify_batch(keyword_texts, model=request.model)

        result_map = {r.keyword.lower(): r.relevant for r in results}
        fresh = rejected = 0

        for kw in keywords:
            is_relevant = result_map.get(kw.keyword.lower(), False)
            if is_relevant:
                kw.status = KeywordStatus.FRESH
                kw.ready_for_scraping = True
                fresh += 1
            else:
                kw.status = KeywordStatus.REJECTED
                kw.ready_for_scraping = False
                rejected += 1

        db.commit()
        return ClassifyResult(total=len(keywords), fresh=fresh, rejected=rejected)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()
