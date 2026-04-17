from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.shared.models import Keyword

async def detect_delta(
    scraped: list[dict],
    session: AsyncSession,
    window_minutes: int,
) -> list[dict]:
    """
    Given a freshly scraped list of keyword dicts, returns only those whose
    lowercase-stripped keyword text did not appear in any keyword row inserted
    within the last `window_minutes` minutes.

    Delta detection is source-agnostic: the same keyword text from a different
    source is NOT a delta if it was already seen in the window.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    result = await session.execute(
        select(Keyword.keyword).where(Keyword.scraped_at > cutoff)
    )
    existing = {k.lower().strip() for k in result.scalars().all()}
    return [kw for kw in scraped if kw["keyword"].lower().strip() not in existing]
