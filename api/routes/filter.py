"""
POST /keywords/filter — Apply rule-based filter to RAW keywords
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import SessionLocal
from models.keyword import Keyword, KeywordStatus
from keyword_scraper.filters import match_rule_filter

router = APIRouter()


class FilterResult(BaseModel):
    total: int
    passed: int
    filtered: int


@router.post("/filter", response_model=FilterResult)
def apply_rule_filter():
    db: Session = SessionLocal()
    try:
        raw_keywords = db.query(Keyword).filter(Keyword.status == KeywordStatus.RAW).all()
        total = len(raw_keywords)
        passed = filtered = 0

        for kw in raw_keywords:
            if match_rule_filter(kw.keyword):
                kw.status = KeywordStatus.FILTERED
                passed += 1
            else:
                db.delete(kw)
                filtered += 1

        db.commit()
        return FilterResult(total=total, passed=passed, filtered=filtered)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()
