import json
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from shared.shared.models import Keyword, Article, KeywordJustification, KeywordEnrichment
from shared.shared.constants import KeywordStatus
from .client import OpenRouterClient, LLMError
from .prompts import build_article_context, build_combined_prompt, build_messages, COMBINED_SYSTEM


async def process_keyword(
    keyword: Keyword,
    articles: list[Article],
    client: OpenRouterClient,
    session: AsyncSession,
) -> None:
    """
    Single LLM call that does justification AND enrichment together.

    Flow:
    - is_relevant=true  → write KeywordJustification + KeywordEnrichment, set status=enriched
    - is_relevant=false → write KeywordJustification only, set status=expired
    - LLM error          → set status=failed with reason
    """
    context = build_article_context(articles)
    prompt = build_combined_prompt(keyword.keyword, context)
    messages = build_messages(COMBINED_SYSTEM, prompt)

    logger.info(
        f"[LLM:PROCESSOR] Starting | keyword_id={keyword.id} | keyword='{keyword.keyword}' | articles={len(articles)}"
    )

    is_relevant = False
    justification = "LLM parse error"
    expanded_keywords: list[str] = []

    try:
        for attempt in range(2):
            try:
                response = await client.chat(messages)

                clean_response = response.strip()
                if clean_response.startswith("```json"):
                    clean_response = clean_response[7:]
                elif clean_response.startswith("```"):
                    clean_response = clean_response[3:]
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]
                clean_response = clean_response.strip()

                data = json.loads(clean_response)

                if "is_relevant" in data:
                    is_relevant = bool(data["is_relevant"])
                    justification = str(data.get("justification", ""))

                    if is_relevant and "expanded_keywords" in data:
                        ek = data["expanded_keywords"]
                        if isinstance(ek, list):
                            expanded_keywords = ek
                    break

            except json.JSONDecodeError:
                logger.warning(f"Processor parse error on attempt {attempt + 1}")
                continue

    except LLMError as e:
        logger.error(f"Processor LLMError: {e}")
        keyword.status = KeywordStatus.FAILED
        keyword.failure_reason = "LLM permanent failure: processor"
        return

    # Always write KeywordJustification
    just_stmt = insert(KeywordJustification).values(
        keyword_id=keyword.id,
        is_relevant=is_relevant,
        justification=justification,
        llm_model=client.model,
    )
    just_stmt = just_stmt.on_conflict_do_update(
        index_elements=["keyword_id"],
        set_={
            "is_relevant": just_stmt.excluded.is_relevant,
            "justification": just_stmt.excluded.justification,
            "llm_model": just_stmt.excluded.llm_model,
        },
    )
    await session.execute(just_stmt)

    if is_relevant:
        source_article_ids = [article.id for article in articles if article.id]

        if not expanded_keywords:
            expanded_keywords = [keyword.keyword]

        enrich_stmt = insert(KeywordEnrichment).values(
            keyword_id=keyword.id,
            expanded_keywords=expanded_keywords,
            source_article_ids=source_article_ids,
            llm_model=client.model,
        )
        enrich_stmt = enrich_stmt.on_conflict_do_update(
            index_elements=["keyword_id"],
            set_={
                "expanded_keywords": enrich_stmt.excluded.expanded_keywords,
                "source_article_ids": enrich_stmt.excluded.source_article_ids,
                "llm_model": enrich_stmt.excluded.llm_model,
            },
        )
        await session.execute(enrich_stmt)
        keyword.status = KeywordStatus.ENRICHED
        logger.info(
            f"[LLM:PROCESSOR] Done (relevant) | keyword_id={keyword.id} | keyword='{keyword.keyword}' | expanded={expanded_keywords}"
        )
    else:
        keyword.status = KeywordStatus.EXPIRED
        logger.info(
            f"[LLM:PROCESSOR] Done (not relevant) | keyword_id={keyword.id} | keyword='{keyword.keyword}'"
        )
