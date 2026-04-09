"""
POST /keywords/{id}/expand — Expand single keyword
POST /keywords/expand/batch — Bulk expand selected keywords
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import SessionLocal
from models.keyword import Keyword, KeywordStatus
from services.expander import expand_batch, DEFAULT_MODEL

router = APIRouter()


class ExpandRequest(BaseModel):
    keyword_ids: list[str]
    model: str = DEFAULT_MODEL


class ExpandResult(BaseModel):
    expanded: int
    variants_created: int


@router.post("/expand/batch", response_model=ExpandResult)
def expand_keywords_batch(request: ExpandRequest):
    db: Session = SessionLocal()
    try:
        keywords = db.query(Keyword).filter(Keyword.id.in_(request.keyword_ids)).all()
        if not keywords:
            raise HTTPException(status_code=404, detail="No keywords found")

        keyword_texts = [kw.keyword for kw in keywords]
        results = expand_batch(keyword_texts, model=request.model)

        result_map = {r.keyword: r.variants for r in results}
        expanded = 0
        variants_created = 0

        for kw in keywords:
            variants = result_map.get(kw.keyword, [])
            if not variants:
                continue

            trigger = "high_trend" if kw.rank <= 5 else "manual"

            for variant_text in variants:
                existing = db.query(Keyword).filter(Keyword.keyword == variant_text).first()
                if existing:
                    continue

                variant_kw = Keyword(
                    keyword=variant_text,
                    source=kw.source,
                    rank=kw.rank,
                    status=KeywordStatus.EXPANDED,
                    expand_trigger=trigger,
                    parent_id=kw.id,
                    ready_for_scraping=True,
                )
                db.add(variant_kw)
                variants_created += 1

            kw.status = KeywordStatus.EXPANDED
            expanded += 1

        db.commit()
        return ExpandResult(expanded=expanded, variants_created=variants_created)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()
