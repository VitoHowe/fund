"""Data normalize pipeline: validate -> map -> enrich -> persist-ready."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


UTC = timezone.utc
SH_TZ = ZoneInfo("Asia/Shanghai")


class DataNormalizer:
    """Normalize envelopes into consistent UTC-based structure."""

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run full normalize pipeline."""
        self._validate(payload)
        mapped = self._map(payload)
        enriched = self._enrich(mapped)
        return enriched

    def _validate(self, payload: dict[str, Any]) -> None:
        required = ("metric", "symbol", "source", "records")
        for key in required:
            if key not in payload:
                raise ValueError(f"normalized payload missing field: {key}")
        if not isinstance(payload.get("records"), list):
            raise ValueError("records must be a list")

    def _map(self, payload: dict[str, Any]) -> dict[str, Any]:
        metric = str(payload.get("metric"))
        canonical_fields = _canonical_fields(metric)
        records: list[dict[str, Any]] = []
        for row in payload.get("records", []):
            mapped = {field: row.get(field) for field in canonical_fields}
            mapped["event_time_utc"] = self._extract_event_time_utc(mapped)
            records.append(mapped)
        copied = dict(payload)
        copied["records"] = records
        copied["source_time"] = self._to_utc_iso(payload.get("source_time"))
        copied["ingest_time"] = self._to_utc_iso(payload.get("ingest_time"))
        return copied

    def _enrich(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("normalized", True)
        metadata.setdefault("timezone_storage", "UTC")
        payload["metadata"] = metadata
        payload["ingest_time"] = payload.get("ingest_time") or datetime.now(tz=UTC).isoformat()
        return payload

    def _extract_event_time_utc(self, row: dict[str, Any]) -> str | None:
        candidates = (
            row.get("event_time_utc"),
            row.get("time"),
            row.get("date"),
            row.get("nav_date"),
            row.get("trade_time"),
        )
        for value in candidates:
            converted = self._to_utc_iso(value)
            if converted:
                return converted
        return None

    def _to_utc_iso(self, value: Any) -> str | None:
        if value in (None, "", "--"):
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=SH_TZ).astimezone(UTC).isoformat()
            return value.astimezone(UTC).isoformat()
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            # unix timestamp seconds/millis
            ts = int(text)
            if ts > 10_000_000_000:
                ts = ts / 1000
            return datetime.fromtimestamp(ts, tz=UTC).isoformat()
        # best-effort parse
        normalized = text.replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
        parsed: datetime | None = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SH_TZ)
        return parsed.astimezone(UTC).isoformat()


def _canonical_fields(metric: str) -> tuple[str, ...]:
    if metric == "history":
        return (
            "date",
            "unit_nav",
            "acc_nav",
            "daily_change_pct",
            "sub_status",
            "red_status",
            "event_time_utc",
        )
    if metric == "realtime":
        return (
            "symbol",
            "name",
            "unit_nav",
            "daily_change_pct",
            "estimated_nav",
            "estimated_change_pct",
            "trade_time",
            "nav_date",
            "event_time_utc",
        )
    if metric == "news":
        return (
            "title",
            "content",
            "time",
            "source",
            "url",
            "relevance",
            "event_time_utc",
        )
    if metric == "flow":
        return (
            "symbol",
            "name",
            "latest_price",
            "volume",
            "amount",
            "change_pct",
            "turnover_pct",
            "market_cap",
            "sector",
            "main_net_inflow",
            "main_inflow_ratio",
            "top_stock",
            "event_time_utc",
        )
    return ("event_time_utc",)
