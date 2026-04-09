"""
POST /keywords/filter — Apply rule-based filter to RAW keywords.
Accepts optional custom signals; defaults to GOVERNANCE_SIGNALS.
Non-matching keywords are marked REJECTED (not deleted).
"""
import re
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import SessionLocal
from models.keyword import Keyword, KeywordStatus
from keyword_scraper.filters import match_rule_filter, GOVERNANCE_SIGNALS

router = APIRouter()


class FilterRequest(BaseModel):
    signals: list[str] | None = None


class FilterResult(BaseModel):
    total: int
    passed: int
    rejected: int


def _match_custom_signals(keyword: str, signals: list[str]) -> bool:
    """Match keyword against a custom list of governance signals."""
    kw_lower = keyword.lower()
    for signal in signals:
        pattern = re.compile(rf"\b{re.escape(signal.strip())}\b", re.IGNORECASE)
        if pattern.search(kw_lower):
            return True
    return False


@router.post("/filter", response_model=FilterResult)
def apply_rule_filter(request: FilterRequest = FilterRequest()):
    db: Session = SessionLocal()
    try:
        raw_keywords = db.query(Keyword).filter(Keyword.status == KeywordStatus.RAW).all()
        total = len(raw_keywords)
        passed = rejected = 0

        use_custom = request.signals is not None and len(request.signals) > 0

        for kw in raw_keywords:
            if use_custom:
                matches = _match_custom_signals(kw.keyword, request.signals)
            else:
                matches = match_rule_filter(kw.keyword)

            if matches:
                kw.status = KeywordStatus.FRESH
                kw.ready_for_scraping = True
                passed += 1
            else:
                kw.status = KeywordStatus.REJECTED
                rejected += 1

        db.commit()
        return FilterResult(total=total, passed=passed, rejected=rejected)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()
