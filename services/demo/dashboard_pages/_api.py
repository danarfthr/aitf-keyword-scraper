"""Shared API client for the dashboard with retry and freshness tracking."""

import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ._models import (
    HealthData,
    KeywordItem,
    EnrichedItem,
    KeywordDetail,
    ArticleItem,
    JustificationItem,
    EnrichmentItem,
    ScrapeRun,
    StuckData,
    StuckAlert,
    ThroughputMetrics,
)


# ── Client ────────────────────────────────────────────────────────────────────

_API_BASE = "http://localhost:8000"

# GMT+7 (WIB — Western Indonesia Time)
WIB = timezone(timedelta(hours=7))


def format_wib(utc_iso: str | None) -> str:
    """Convert UTC ISO timestamp to 'YYYY-MM-DD HH:MM:SS WIB' in GMT+7."""
    if not utc_iso:
        return "—"
    try:
        utc_str = utc_iso.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(utc_str).astimezone(timezone.utc)
        dt_wib = dt_utc.astimezone(WIB)
        return dt_wib.strftime("%Y-%m-%d %H:%M:%S") + " WIB"
    except (ValueError, TypeError):
        return utc_iso[:19] if utc_iso else "—"


def set_api_base(url: str):
    global _API_BASE
    _API_BASE = url


def _get(path: str, params: dict | None = None, retries: int = 2) -> dict[str, Any]:
    for attempt in range(retries):
        try:
            r = httpx.get(f"{_API_BASE}{path}", params=params or {}, timeout=15.0)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                return {}
            time.sleep(0.5 * (attempt + 1))
    return {}


def _now() -> float:
    return time.time()


# ── Health ────────────────────────────────────────────────────────────────────

def get_health() -> HealthData:
    raw = _get("/pipeline/health")
    counts: dict[str, int] = raw.get("counts", {})
    last = raw.get("last_scrape") or {}
    scrape = ScrapeRun(
        scrape_run_id=last.get("scrape_run_id"),
        source=last.get("source"),
        started_at=last.get("started_at"),
        finished_at=last.get("finished_at"),
        keywords_inserted=last.get("keywords_inserted") or 0,
        status=last.get("status"),
    )
    return HealthData(counts=counts, last_scrape=scrape, fetched_at=_now())


def get_stuck() -> StuckData | None:
    raw = _get("/pipeline/stuck")
    if not raw:
        return None
    stuck_kws = [
        StuckAlert(
            level=a["level"],
            status=a["status"],
            count=a["count"],
            oldest_seconds=a["oldest_seconds"],
            message=a["message"],
        )
        for a in raw.get("stuck_keywords", [])
    ]
    tp = raw.get("throughput", {})
    throughput = ThroughputMetrics(
        keywords_per_minute=tp.get("keywords_per_minute", 0.0),
        avg_cycle_duration_seconds=tp.get("avg_cycle_duration_seconds", 0.0),
        total_runs_24h=tp.get("total_runs_24h", 0),
        total_keywords_24h=tp.get("total_keywords_24h", 0),
    )
    return StuckData(
        stuck_keywords=stuck_kws,
        throughput=throughput,
        stale_threshold_seconds=raw.get("stale_threshold_seconds", 1800),
        fetched_at=_now(),
    )


# ── Keywords ───────────────────────────────────────────────────────────────────

def get_keywords_by_status(
    status: str,
    limit: int = 200,
    since: str | None = None,
    source: str | None = None,
    include_relevant: bool = False,
) -> tuple[list[KeywordItem], float]:
    params: dict[str, Any] = {"limit": limit}
    if since:
        params["since"] = since
    if source:
        params["source"] = source
    if include_relevant:
        params["include_relevant"] = "true"

    raw = _get(f"/keywords/status/{status}", params)
    fetched_at = _now()
    items = []
    for it in raw.get("items", []):
        items.append(
            KeywordItem(
                id=it["id"],
                keyword=it["keyword"],
                source=it["source"],
                rank=it.get("rank"),
                scraped_at=it.get("scraped_at", ""),
                status=status,
                expanded_keywords=it.get("expanded_keywords", []),
                is_relevant=it.get("is_relevant"),
            )
        )
    return items, fetched_at


def get_enriched(
    limit: int = 200,
    since: str | None = None,
    source: str | None = None,
) -> tuple[list[EnrichedItem], float]:
    params: dict[str, Any] = {"limit": limit}
    if since:
        params["since"] = since
    if source:
        params["source"] = source

    raw = _get("/keywords/enriched", params)
    fetched_at = _now()
    items = []
    for it in raw.get("items", []):
        items.append(
            EnrichedItem(
                id=it["id"],
                keyword=it["keyword"],
                source=it["source"],
                rank=it.get("rank"),
                scraped_at=it.get("scraped_at", ""),
                expanded_keywords=it.get("expanded_keywords", []),
            )
        )
    return items, fetched_at


def get_keyword_detail(keyword_id: int) -> KeywordDetail | None:
    raw = _get(f"/keywords/{keyword_id}")
    if not raw:
        return None
    articles = [
        ArticleItem(
            id=a["id"],
            source_site=a["source_site"],
            url=a["url"],
            title=a.get("title"),
            crawled_at=a.get("crawled_at", ""),
        )
        for a in raw.get("articles", [])
    ]
    just_raw = raw.get("justification")
    justification = None
    if just_raw:
        justification = JustificationItem(
            is_relevant=just_raw["is_relevant"],
            justification=just_raw.get("justification"),
            llm_model=just_raw.get("llm_model", ""),
            processed_at=just_raw.get("processed_at", ""),
        )
    enrich_raw = raw.get("enrichment")
    enrichment = None
    if enrich_raw:
        enrichment = EnrichmentItem(
            expanded_keywords=enrich_raw.get("expanded_keywords", []),
            llm_model=enrich_raw.get("llm_model", ""),
            processed_at=enrich_raw.get("processed_at", ""),
        )
    return KeywordDetail(
        id=raw["id"],
        keyword=raw["keyword"],
        source=raw["source"],
        rank=raw.get("rank"),
        status=raw["status"],
        failure_reason=raw.get("failure_reason"),
        scraped_at=raw.get("scraped_at", ""),
        updated_at=raw.get("updated_at", ""),
        articles=articles,
        justification=justification,
        enrichment=enrichment,
    )
