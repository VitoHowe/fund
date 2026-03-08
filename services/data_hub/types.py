"""Normalized data contracts for cross-source responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    """Return UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SourceHealth:
    """Runtime source health snapshot."""

    source: str
    priority: int
    supported_metrics: list[str] = field(default_factory=list)
    enabled: bool = True
    status: str = "not_requested"
    route_state: str = "idle"
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    last_metric: str | None = None
    last_error: str | None = None
    last_success_time: str | None = None
    last_failure_time: str | None = None
    circuit_open_until: str | None = None
    avg_latency_ms: float | None = None
    latency_ms: float | None = None
    fallback_source: str | None = None
    quality_score: float | None = None
    error_message: str | None = None
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NormalizedEnvelope:
    """Unified output schema across all data sources."""

    metric: str
    symbol: str
    source: str
    source_time: str | None
    records: list[dict[str, Any]]
    quality_score: float = 1.0
    stale: bool = False
    ingest_time: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

