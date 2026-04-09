import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Source(str, PyEnum):
    GTR = "GTR"
    T24 = "T24"
    MANUAL = "MANUAL"


class KeywordStatus(str, PyEnum):
    RAW = "raw"
    FILTERED = "filtered"
    REJECTED = "rejected"
    FRESH = "fresh"
    EXPANDED = "expanded"


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    keyword: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source: Mapped[Source] = mapped_column(Enum(Source), nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[KeywordStatus] = mapped_column(Enum(KeywordStatus), default=KeywordStatus.RAW, index=True)
    expand_trigger: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("keywords.id"), nullable=True)
    ready_for_scraping: Mapped[bool] = mapped_column(Boolean, default=False)
