from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .constants import KeywordStatus, KeywordSource, ArticleSource, ARTICLE_SOURCES


class Base(DeclarativeBase):
    pass


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, CheckConstraint(f"source IN ('{KeywordSource.TRENDS24}', '{KeywordSource.GOOGLE_TRENDS}')"), nullable=False
    )
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text,
        CheckConstraint(
            f"status IN ('{KeywordStatus.RAW}', '{KeywordStatus.NEWS_SAMPLED}', "
            f"'{KeywordStatus.LLM_JUSTIFIED}', '{KeywordStatus.ENRICHED}', "
            f"'{KeywordStatus.EXPIRED}', '{KeywordStatus.FAILED}')"
        ),
        server_default=KeywordStatus.RAW,
        nullable=False,
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    articles: Mapped[list["Article"]] = relationship(
        "Article", back_populates="keyword", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_keywords_status", "status"),
        Index("idx_keywords_scraped_at", "scraped_at"),
        Index("idx_keywords_status_updated", "status", "updated_at"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False
    )
    source_site: Mapped[str] = mapped_column(
        Text, CheckConstraint(
            f"source_site IN ({', '.join(repr(s) for s in ARTICLE_SOURCES)})"
        ), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    
    keyword: Mapped["Keyword"] = relationship("Keyword", back_populates="articles")

    __table_args__ = (
        Index("idx_articles_keyword_id", "keyword_id"),
        # uq_articles_url is implicitly handled by unique=True
    )


class KeywordJustification(Base):
    __tablename__ = "keyword_justifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("keywords.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    is_relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    justification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_justifications_is_relevant", "is_relevant"),
        # uq_justifications_keyword_id is implicitly handled by unique=True
    )


class KeywordEnrichment(Base):
    __tablename__ = "keyword_enrichments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("keywords.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    expanded_keywords: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    source_article_ids: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # UNIQUE on keyword_id is handled by unique=True


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(
        Text, CheckConstraint("source IN ('trends24', 'google_trends', 'all')"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    keywords_inserted: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        CheckConstraint("status IN ('running', 'done', 'failed')"),
        server_default="running",
        nullable=False,
    )

    __table_args__ = (
        Index("idx_scrape_runs_started_at", "started_at"),
        Index("idx_scrape_runs_status", "status"),
    )
