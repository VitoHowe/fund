"""Unified schema for news pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class NewsItem:
    """Normalized news item."""

    uid: str
    title: str
    content: str
    published_at_utc: str
    source: str
    source_channel: str
    url: str | None = None
    symbols: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    relevance_score: float = 0.0
    credibility_tier: str = "B"
    ingest_time_utc: str = field(default_factory=now_utc_iso)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NewsFeatureSummary:
    """Aggregated news features for factor input."""

    symbol: str
    rows: int
    avg_sentiment: float
    positive_ratio: float
    negative_ratio: float
    credibility_weighted_sentiment: float
    latest_news_time_utc: str | None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

