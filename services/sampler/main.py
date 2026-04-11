import asyncio
import os
import time

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from shared.shared.constants import (
    MAX_ARTICLES_TOTAL_PER_KEYWORD,
    KeywordStatus,
)
from shared.shared.db import get_session
from shared.shared.models import Article, Keyword

from .crawler import crawl_detik, crawl_kompas, crawl_tribun
from .summarizer import summarize_body

SAMPLER_POLL_INTERVAL_SECONDS = int(os.environ.get("SAMPLER_POLL_INTERVAL_SECONDS", "30"))
SAMPLER_BATCH_SIZE = int(os.environ.get("SAMPLER_BATCH_SIZE", "5"))

async def process_keyword(session, keyword: Keyword):
    try:
        results = await asyncio.gather(
            crawl_detik(keyword.keyword),
            crawl_kompas(keyword.keyword),
            crawl_tribun(keyword.keyword),
            return_exceptions=True,
        )
        
        all_articles = []
        for r in results:
            if isinstance(r, list):
                all_articles.extend(r)
                
        # Deduplicate
        seen_urls = set()
        deduped = []
        for a in all_articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                deduped.append(a)
                
        selected = deduped[:MAX_ARTICLES_TOTAL_PER_KEYWORD]
        
        for art in selected:
            body_to_store, summary_to_store = summarize_body(art["body"])
            stmt = insert(Article).values(
                keyword_id=keyword.id,
                source_site=art["source_site"],
                url=art["url"],
                title=art["title"],
                body=body_to_store,
                summary=summary_to_store,
            ).on_conflict_do_nothing(index_elements=["url"])
            await session.execute(stmt)
            
        keyword.status = KeywordStatus.NEWS_SAMPLED
        if not selected:
            logger.warning(f"No articles found for keyword: {keyword.keyword}")
            
    except Exception as e:
        logger.error(f"Error processing keyword {keyword.keyword}: {e}")
        keyword.status = KeywordStatus.FAILED
        keyword.failure_reason = str(e)

async def run_sampler():
    logger.info(f"sampler started. Poll interval={SAMPLER_POLL_INTERVAL_SECONDS}s, batch size={SAMPLER_BATCH_SIZE}")
    while True:
        try:
            async with get_session() as session:
                async with session.begin():
                    result = await session.execute(
                        select(Keyword)
                        .where(Keyword.status == KeywordStatus.RAW)
                        .order_by(Keyword.scraped_at.asc())
                        .limit(SAMPLER_BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                    keywords = result.scalars().all()
                    
                    for kw in keywords:
                        await process_keyword(session, kw)
                        
            # Heartbeat
            with open("/tmp/sampler_heartbeat.txt", "w") as f:
                f.write(str(time.time()))
                
        except Exception as e:
            logger.error(f"Sampler loop error: {e}")
            
        await asyncio.sleep(SAMPLER_POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(run_sampler())
