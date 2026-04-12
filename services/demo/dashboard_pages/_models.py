"""Typed response models for the dashboard."""

from dataclasses import dataclass, field


@dataclass
class KeywordItem:
    id: int
    keyword: str
    source: str
    rank: int | None
    scraped_at: str
    status: str
    expanded_keywords: list[str] = field(default_factory=list)
    is_relevant: bool | None = None


@dataclass
class EnrichedItem:
    id: int
    keyword: str
    source: str
    rank: int | None
    scraped_at: str
    expanded_keywords: list[str]


@dataclass
class ArticleItem:
    id: int
    source_site: str
    url: str
    title: str | None
    crawled_at: str


@dataclass
class JustificationItem:
    is_relevant: bool
    justification: str | None
    llm_model: str
    processed_at: str


@dataclass
class EnrichmentItem:
    expanded_keywords: list[str]
    llm_model: str
    processed_at: str


@dataclass
class KeywordDetail:
    id: int
    keyword: str
    source: str
    rank: int | None
    status: str
    failure_reason: str | None
    scraped_at: str
    updated_at: str
    articles: list[ArticleItem] = field(default_factory=list)
    justification: JustificationItem | None = None
    enrichment: EnrichmentItem | None = None


@dataclass
class ScrapeRun:
    scrape_run_id: int | None
    source: str | None
    started_at: str | None
    finished_at: str | None
    keywords_inserted: int
    status: str | None


@dataclass
class HealthData:
    counts: dict[str, int]
    last_scrape: ScrapeRun | None
    fetched_at: float  # Unix timestamp when fetched


@dataclass
class StuckAlert:
    level: str  # "critical" | "warning" | "info"
    status: str
    count: int
    oldest_seconds: int
    message: str


@dataclass
class ThroughputMetrics:
    keywords_per_minute: float
    avg_cycle_duration_seconds: float
    total_runs_24h: int
    total_keywords_24h: int


@dataclass
class StuckData:
    stuck_keywords: list[StuckAlert]
    throughput: ThroughputMetrics
    stale_threshold_seconds: int
    fetched_at: float
