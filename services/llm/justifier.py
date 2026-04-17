import json
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from shared.shared.models import Keyword, Article, KeywordJustification
from shared.shared.constants import KeywordStatus
from .client import OpenRouterClient, LLMError
from .prompts import build_article_context, build_justifier_prompt, build_messages, JUSTIFIER_SYSTEM

async def justify_keyword(
    keyword: Keyword,
    articles: list[Article],
    client: OpenRouterClient,
    session: AsyncSession,
) -> None:
    """
    Determines if keyword topic is related to Indonesian government issues.
    Saves KeywordJustification row. Updates keyword status to llm_justified.
    On LLMError: sets status = failed with reason.
    """
    context = build_article_context(articles)
    prompt = build_justifier_prompt(keyword.keyword, context)
    messages = build_messages(JUSTIFIER_SYSTEM, prompt)
    
    is_relevant = False
    justification = "LLM parse error"
    
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
                
                if "is_relevant" in data:
                    is_relevant = bool(data["is_relevant"])
                    justification = str(data.get("justification", ""))
                    break
                    
            except json.JSONDecodeError:
                logger.warning(f"Justifier parse error on attempt {attempt + 1}")
                continue
                
    except LLMError as e:
        logger.error(f"Justifier LLMError: {e}")
        keyword.status = KeywordStatus.FAILED
        keyword.failure_reason = "LLM permanent failure: justifier"
        return

    # Insert KeywordJustification
    stmt = insert(KeywordJustification).values(
        keyword_id=keyword.id,
        is_relevant=is_relevant,
        justification=justification,
        llm_model=client.model
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["keyword_id"],
        set_={
            "is_relevant": stmt.excluded.is_relevant,
            "justification": stmt.excluded.justification,
            "llm_model": stmt.excluded.llm_model,
        }
    )
    await session.execute(stmt)
    
    keyword.status = KeywordStatus.LLM_JUSTIFIED
