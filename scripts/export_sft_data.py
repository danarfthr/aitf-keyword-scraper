"""
Export SFT training data from keyword-scraper-3 database.

Produces: data/sft/keyword-scraper-3/sft.jsonl

Each line: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

Usage:
  docker compose run --rm -w /app llm python scripts/export_sft_data.py
"""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from shared.shared.db import get_session
from shared.shared.models import Keyword, KeywordJustification, KeywordEnrichment, Article
from shared.shared.constants import KeywordStatus


OUTPUT_FILE = Path("data/sft/keyword-scraper-3/sft.jsonl")
SYSTEM_PROMPT = """
You are a content relevance and keyword expansion assistant for a government
issue monitoring system operated by the Indonesian Ministry of Communication
and Informatics (Komdigi).

You will receive a keyword and sample news articles about it.

Step 1 — RELEVANCE: Determine whether this keyword topic is related to
Indonesian government affairs. Relevant topics include: ministry activities,
public policy, regulations, government programs, state-owned enterprises (BUMN),
parliamentary proceedings, court rulings affecting public policy, or
government-linked institutions. Base your decision on the article content,
not just the keyword text alone.

Step 2 — EXPANSION: If relevant, generate related search keywords that will
help a crawler find more government-relevant articles on the same topic.

Rules for expansion:
- Generate 5 to 10 expanded keywords.
- All keywords must be in Indonesian.
- Base keywords strictly on the article content — do not invent unrelated terms.
- Each keyword must be specific and directly related to the government topic.
- Avoid generic terms such as: "berita", "indonesia", "terbaru", "informasi".
- Keep each keyword concise: 1 to 4 words.

Respond ONLY with a valid JSON object. No text before or after the JSON.

Format when not relevant:
{"is_relevant": false, "justification": "<reason in Indonesian, max 2 sentences>"}

Format when relevant:
{"is_relevant": true, "justification": "<reason in Indonesian, max 2 sentences>", "expanded_keywords": ["keyword1", "keyword2", "keyword3"]}
"""


def build_article_context(articles: list[Article]) -> str:
    from shared.shared.constants import SUMMARY_CHAR_THRESHOLD
    parts = []
    for i, article in enumerate(articles, 1):
        content = article.summary if article.summary else (article.body or "")[:SUMMARY_CHAR_THRESHOLD]
        title = article.title or "(no title)"
        parts.append(f"[Artikel {i}] {title}\n{content}")
    return "\n\n".join(parts)


def build_user_prompt(keyword: str, article_context: str) -> str:
    return f"""Keyword trending: {keyword}

Sampel artikel:
{article_context}

Tahap 1 — Apakah keyword ini berkaitan dengan isu pemerintahan Indonesia?
Tahap 2 — Jika ya, hasilkan keyword pencarian tambahan yang relevan."""


async def export_sft_data():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    count = 0
    async with get_session() as session:
        # Keywords that have a KeywordJustification row
        # Get ALL keywords that have a KeywordJustification row (any status)
        result = await session.execute(
            select(Keyword)
            .join(KeywordJustification, Keyword.id == KeywordJustification.keyword_id)
            .options(selectinload(Keyword.articles))
        )
        keywords = result.scalars().all()

        keyword_ids = [kw.id for kw in keywords]
        logger.info(f"Found {len(keywords)} keywords to export")

        # Batch load justifications and enrichments
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

            article_context = build_article_context(articles)
            user_prompt = build_user_prompt(keyword.keyword, article_context)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            assistant_content = {"is_relevant": justification.is_relevant}
            if justification.justification:
                assistant_content["justification"] = justification.justification
            if enrichment and enrichment.expanded_keywords:
                assistant_content["expanded_keywords"] = enrichment.expanded_keywords

            record = {
                "messages": messages + [{"role": "assistant", "content": json.dumps(assistant_content, ensure_ascii=False)}]
            }

            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    logger.info(f"Export complete. Records: {count}")
    logger.info(f"File written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(export_sft_data())