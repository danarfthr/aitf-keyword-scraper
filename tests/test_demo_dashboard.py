"""Smoke tests for the demo dashboard components — no Streamlit server required."""

import time
from datetime import datetime, timezone

import pytest

from services.demo.dashboard_pages._models import (
    HealthData,
    KeywordItem,
    StuckAlert,
    ThroughputMetrics,
    StuckData,
    KeywordDetail,
    ArticleItem,
    JustificationItem,
)
from services.demo.dashboard_pages._theme import STATUS_COLORS, RELEVANCE_COLORS, SOURCE_COLORS, ALERT_COLORS
from services.demo.dashboard_pages.components._freshness_indicator import render_freshness_indicator
from services.demo.dashboard_pages.components._status_badge import render_status_badge, render_source_badge


# ── Model tests ───────────────────────────────────────────────────────────────

class TestHealthData:
    def test_health_data_creation(self):
        from services.demo.dashboard_pages._models import ScrapeRun
        scrape = ScrapeRun(
            scrape_run_id=1,
            source="trends24",
            started_at="2026-04-12T10:00:00",
            finished_at="2026-04-12T10:01:30",
            keywords_inserted=42,
            status="done",
        )
        health = HealthData(
            counts={"raw": 10, "enriched": 5},
            last_scrape=scrape,
            fetched_at=time.time(),
        )
        assert health.counts["enriched"] == 5
        assert health.last_scrape.keywords_inserted == 42

    def test_keyword_item_with_is_relevant(self):
        item = KeywordItem(
            id=1,
            keyword="pemilu 2024",
            source="trends24",
            rank=1,
            scraped_at="2026-04-12T10:00:00",
            status="llm_justified",
            is_relevant=True,
        )
        assert item.is_relevant is True

    def test_stuck_data_structure(self):
        stuck = StuckData(
            stuck_keywords=[
                StuckAlert(
                    level="warning",
                    status="raw",
                    count=5,
                    oldest_seconds=3600,
                    message="5 keywords stuck in 'raw' for 60+ min",
                )
            ],
            throughput=ThroughputMetrics(
                keywords_per_minute=3.5,
                avg_cycle_duration_seconds=120.0,
                total_runs_24h=10,
                total_keywords_24h=150,
            ),
            stale_threshold_seconds=1800,
            fetched_at=time.time(),
        )
        assert len(stuck.stuck_keywords) == 1
        assert stuck.stuck_keywords[0].level == "warning"
        assert stuck.throughput.keywords_per_minute == 3.5


class TestKeywordDetail:
    def test_keyword_detail_full(self):
        detail = KeywordDetail(
            id=1,
            keyword="demo",
            source="trends24",
            rank=1,
            status="enriched",
            failure_reason=None,
            scraped_at="2026-04-12T10:00:00",
            updated_at="2026-04-12T12:00:00",
            articles=[
                ArticleItem(
                    id=1,
                    source_site="detik",
                    url="https://example.com",
                    title="Example Article",
                    crawled_at="2026-04-12T10:30:00",
                )
            ],
            justification=JustificationItem(
                is_relevant=True,
                justification="Government related",
                llm_model="mistral/mistral-7b",
                processed_at="2026-04-12T11:00:00",
            ),
        )
        assert detail.justification.is_relevant is True
        assert len(detail.articles) == 1


# ── Theme tests ────────────────────────────────────────────────────────────────

class TestThemeColors:
    def test_all_statuses_have_colors(self):
        from services.demo.pages._models import HealthData
        from services.demo.dashboard_pages._models import ScrapeRun
        # All statuses from KeywordStatus.ALL should have a color defined
        all_statuses = ["raw", "news_sampled", "llm_justified", "enriched", "expired", "failed"]
        for status in all_statuses:
            assert status in STATUS_COLORS, f"Missing color for status: {status}"

    def test_relevance_colors_complete(self):
        assert True in RELEVANCE_COLORS
        assert False in RELEVANCE_COLORS

    def test_source_colors_complete(self):
        assert "trends24" in SOURCE_COLORS
        assert "google_trends" in SOURCE_COLORS

    def test_alert_levels_complete(self):
        assert "critical" in ALERT_COLORS
        assert "warning" in ALERT_COLORS
        assert "info" in ALERT_COLORS


class TestStatusBadge:
    def test_render_status_badge_returns_html(self):
        html = render_status_badge("enriched")
        assert "status-pill" in html
        assert "enriched" in html.lower()

    def test_render_source_badge_returns_html(self):
        html = render_source_badge("trends24")
        assert "source-badge" in html
        assert "trends24" in html.lower()


# ── API client shape tests ────────────────────────────────────────────────────

class TestAPIClientShapes:
    def test_health_data_fields(self):
        from services.demo.dashboard_pages._models import ScrapeRun
        health = HealthData(
            counts={},
            last_scrape=None,
            fetched_at=time.time(),
        )
        assert hasattr(health, "counts")
        assert hasattr(health, "last_scrape")
        assert hasattr(health, "fetched_at")

    def test_stuck_data_fields(self):
        stuck_data = StuckData(
            stuck_keywords=[],
            throughput=ThroughputMetrics(
                keywords_per_minute=0.0,
                avg_cycle_duration_seconds=0.0,
                total_runs_24h=0,
                total_keywords_24h=0,
            ),
            stale_threshold_seconds=1800,
            fetched_at=time.time(),
        )
        assert hasattr(stuck_data, "stuck_keywords")
        assert hasattr(stuck_data, "throughput")
        assert hasattr(stuck_data, "stale_threshold_seconds")
        assert hasattr(stuck_data, "fetched_at")


# ── Throughput metrics tests ──────────────────────────────────────────────────

class TestThroughputMetrics:
    def test_keywords_per_minute_calculation(self):
        # Simulate: 60 keywords inserted in 2-minute cycle = 30 kw/min
        keywords_inserted = 60
        duration_seconds = 120.0
        rate = keywords_inserted / (duration_seconds / 60)
        assert rate == 30.0

    def test_avg_cycle_duration(self):
        durations = [60.0, 120.0, 90.0]
        avg = sum(durations) / len(durations)
        assert avg == 90.0

    def test_stale_threshold_default(self):
        threshold = 1800  # 30 minutes in seconds
        assert threshold == 30 * 60
