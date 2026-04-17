"""
Export SFT training data from the keyword-scraper-2 database.

Produces two JSONL files:
  - data/sft/keyword-scraper-2/justifier_sft.jsonl
  - data/sft/keyword-scraper-2/enricher_sft.jsonl

Each line is a JSON object with a "messages" array matching the OpenAI fine-tuning format:
  {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

Usage:
  PYTHONPATH=. python scripts/export_sft_data.py
  # Or with docker-compose:
  docker compose run --rm llm python scripts/export_sft_data.py
"""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordJustification, KeywordEnrichment
from shared.shared.constants import KeywordStatus
from services.llm.prompts import (
    JUSTIFIER_SYSTEM,
    ENRICHER_SYSTEM,
    build_justifier_prompt,
    build_enricher_prompt,
    build_article_context,
    build_messages,
)


OUTPUT_DIR = Path("data/sft/keyword-scraper-2")
JUSTIFIER_OUTPUT = OUTPUT_DIR / "justifier_sft.jsonl"
ENRICHER_OUTPUT = OUTPUT_DIR / "enricher_sft.jsonl"


async def export_sft_data():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing files so we start fresh
    for path in [JUSTIFIER_OUTPUT, ENRICHER_OUTPUT]:
        if path.exists():
            path.unlink()

    justification_count = 0
    enricher_count = 0

    async with get_session() as session:
        # Fetch all keywords that have a KeywordJustification row
        result = await session.execute(
            select(Keyword)
            .join(KeywordJustification, Keyword.id == KeywordJustification.keyword_id)
            .where(Keyword.status.in_([KeywordStatus.LLM_JUSTIFIED, KeywordStatus.ENRICHED]))
            .options(selectinload(Keyword.articles))
        )
        keywords = result.scalars().all()
        keyword_ids = [kw.id for kw in keywords]
        logger.info(f"Found {len(keywords)} keywords with justifications to export")

        # Batch-load justifications and enrichments
        justifications_result = await session.execute(
            select(KeywordJustification).where(KeywordJustification.keyword_id.in_(keyword_ids))
        )
        justifications = {j.keyword_id: j for j in justifications_result.scalars().all()}

        enrichments_result = await session.execute(
            select(KeywordEnrichment).where(KeywordEnrichment.keyword_id.in_(keyword_ids))
        )
        enrichments = {e.keyword_id: e for e in enrichments_result.scalars().all()}

        for keyword in keywords:
            articles = list(keyword.articles)
            justification = justifications.get(keyword.id)
            enrichment = enrichments.get(keyword.id)

            if not justification:
                continue

            # --- Justifier record ---
            article_context = build_article_context(articles)
            user_prompt = build_justifier_prompt(keyword.keyword, article_context)
            messages = build_messages(JUSTIFIER_SYSTEM, user_prompt)

            assistant_content = json.dumps({
                "is_relevant": justification.is_relevant,
                "justification": justification.justification or "",
            }, ensure_ascii=False)

            justifier_record = {
                "messages": messages + [{"role": "assistant", "content": assistant_content}]
            }

            with open(JUSTIFIER_OUTPUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(justifier_record, ensure_ascii=False) + "\n")
            justification_count += 1

            # --- Enricher record (only for relevant, enriched keywords) ---
            if enrichment and justification.is_relevant:
                article_context = build_article_context(articles)
                user_prompt = build_enricher_prompt(keyword.keyword, article_context)
                messages = build_messages(ENRICHER_SYSTEM, user_prompt)

                assistant_content = json.dumps({
                    "expanded_keywords": enrichment.expanded_keywords or [],
                }, ensure_ascii=False)

                enricher_record = {
                    "messages": messages + [{"role": "assistant", "content": assistant_content}]
                }

                with open(ENRICHER_OUTPUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(enricher_record, ensure_ascii=False) + "\n")
                enricher_count += 1

    logger.info(
        f"Export complete. Justifier records: {justification_count}, "
        f"Enricher records: {enricher_count}"
    )
    logger.info(f"Files written to: {JUSTIFIER_OUTPUT} and {ENRICHER_OUTPUT}")


if __name__ == "__main__":
    asyncio.run(export_sft_data())
