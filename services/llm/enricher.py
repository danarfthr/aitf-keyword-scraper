import json
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from shared.shared.models import Keyword, Article, KeywordEnrichment
from shared.shared.constants import KeywordStatus
from .client import OpenRouterClient, LLMError
from .prompts import build_article_context, build_enricher_prompt, build_messages, ENRICHER_SYSTEM

async def enrich_keyword(
    keyword: Keyword,
    articles: list[Article],
    client: OpenRouterClient,
    session: AsyncSession,
) -> None:
    """
    Expands a relevant keyword into broader search queries using LLM.
    Saves KeywordEnrichment row. Updates keyword status to llm_enriched.
    On LLMError: sets status = failed with reason.
    """
    context = build_article_context(articles)
    prompt = build_enricher_prompt(keyword.keyword, context)
    messages = build_messages(ENRICHER_SYSTEM, prompt)
    
    expanded_keywords = []
    
    try:
        for attempt in range(2):
            try:
                response = await client.chat(messages)
                
                # Cleanup potential markdown json fences
                clean_response = response.strip()
                if clean_response.startswith("```json"):
                    clean_response = clean_response[7:]
                elif clean_response.startswith("```"):
                    clean_response = clean_response[3:]
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]
                clean_response = clean_response.strip()
                
                data = json.loads(clean_response)
                
                if "expanded_keywords" in data and isinstance(data["expanded_keywords"], list):
                    expanded_keywords = data["expanded_keywords"]
                    break
                    
            except json.JSONDecodeError:
                logger.warning(f"Enricher parse error on attempt {attempt + 1}")
                continue
                
    except LLMError as e:
        logger.error(f"Enricher LLMError: {e}")
        keyword.status = KeywordStatus.FAILED
        keyword.failure_reason = "LLM permanent failure: enricher"
        return

    # Extract source article IDs representing the context we sent
    source_article_ids = [article.id for article in articles if article.id]

    # Insert KeywordEnrichment
    stmt = insert(KeywordEnrichment).values(
        keyword_id=keyword.id,
        expanded_keywords=expanded_keywords,
        source_article_ids=source_article_ids,
        llm_model=client.model
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["keyword_id"],
        set_={
            "expanded_keywords": stmt.excluded.expanded_keywords,
            "source_article_ids": stmt.excluded.source_article_ids,
            "llm_model": stmt.excluded.llm_model,
        }
    )
    await session.execute(stmt)
    
    keyword.status = KeywordStatus.ENRICHED
