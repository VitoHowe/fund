"""Cache policy and cache metrics for real-time and batch workloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


SH_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class CacheMetrics:
    """Cache operational metrics."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0
    expired: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class CachePolicy:
    """Provide TTL by metric and market time window."""

    def __init__(self) -> None:
        self._trading_ttl = {
            "realtime": 5,
            "history": 60,
            "news": 120,
            "flow": 20,
        }
        self._offhours_ttl = {
            "realtime": 90,
            "history": 3600,
            "news": 900,
            "flow": 300,
        }

    def get_ttl_seconds(self, metric: str, now: datetime | None = None) -> int:
        """Return cache ttl based on metric and session."""
        now = now or datetime.now(tz=SH_TZ)
        if self._is_trading_time(now):
            return self._trading_ttl.get(metric, 60)
        return self._offhours_ttl.get(metric, 300)

    @staticmethod
    def _is_trading_time(now: datetime) -> bool:
        if now.tzinfo is None:
            now = now.replace(tzinfo=SH_TZ)
        local = now.astimezone(SH_TZ)
        if local.weekday() >= 5:
            return False
        current = local.hour * 60 + local.minute
        morning_open = 9 * 60 + 30
        morning_close = 11 * 60 + 30
        afternoon_open = 13 * 60
        afternoon_close = 15 * 60
        return (morning_open <= current <= morning_close) or (
            afternoon_open <= current <= afternoon_close
        )

