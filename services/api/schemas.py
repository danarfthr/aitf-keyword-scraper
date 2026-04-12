"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel
from typing import Optional


class TriggerRequest(BaseModel):
    source: str  # "trends24", "google_trends", or "all"


class TriggerResponse(BaseModel):
    triggered: bool
    scrape_run_id: Optional[int] = None
    message: str


class ExpireResponse(BaseModel):
    triggered: bool
    message: str


class RetryFailedResponse(BaseModel):
    reset_count: int


class HealthResponse(BaseModel):
    counts: dict
    last_scrape: Optional[dict]


class EnrichedKeywordItem(BaseModel):
    id: int
    keyword: str
    source: str
    rank: Optional[int]
    scraped_at: str
    expanded_keywords: list[str]
    is_relevant: Optional[bool] = None  # Only populated when include_relevant=true on llm_justified


class EnrichedListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EnrichedKeywordItem]


class ArticleItem(BaseModel):
    id: int
    source_site: str
    url: str
    title: Optional[str]
    crawled_at: str


class JustificationItem(BaseModel):
    is_relevant: bool
    justification: Optional[str]
    llm_model: str
    processed_at: str


class EnrichmentItem(BaseModel):
    expanded_keywords: list[str]
    llm_model: str
    processed_at: str


class KeywordDetailResponse(BaseModel):
    id: int
    keyword: str
    source: str
    rank: Optional[int]
    status: str
    failure_reason: Optional[str]
    scraped_at: str
    updated_at: str
    articles: list[ArticleItem]
    justification: Optional[JustificationItem]
    enrichment: Optional[EnrichmentItem]


# --- Stuck Keywords & Throughput ---

class StuckAlert(BaseModel):
    level: str  # "critical" | "warning" | "info"
    status: str
    count: int
    oldest_seconds: int
    message: str


class ThroughputMetrics(BaseModel):
    keywords_per_minute: float
    avg_cycle_duration_seconds: float
    total_runs_24h: int
    total_keywords_24h: int


class StuckKeywordsResponse(BaseModel):
    stuck_keywords: list[StuckAlert]
    throughput: ThroughputMetrics
    stale_threshold_seconds: int
