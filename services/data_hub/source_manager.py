"""Source manager with fallback, retries and circuit breaker."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.cache_policy import CachePolicy
from services.data_hub.exceptions import DataUnavailableError
from services.data_hub.normalizer import DataNormalizer
from services.data_hub.repository import DataRepository
from services.data_hub.types import SourceHealth, now_iso


@dataclass(slots=True)
class SourceManagerConfig:
    """Runtime config for source routing."""

    failure_threshold: int = 3
    cooldown_seconds: int = 90
    retry_per_source: int = 1
    timeout_seconds: int = 20


class SourceManager:
    """Manage source fallback and health."""

    def __init__(
        self,
        adapters: list[IDataSourceAdapter],
        config: SourceManagerConfig | None = None,
        repository: DataRepository | None = None,
        normalizer: DataNormalizer | None = None,
        cache_policy: CachePolicy | None = None,
    ) -> None:
        self.config = config or SourceManagerConfig()
        self.adapters = sorted(adapters, key=lambda a: a.priority)
        self.cache_policy = cache_policy or CachePolicy()
        self.repository = repository or DataRepository(cache_policy=self.cache_policy)
        self.normalizer = normalizer or DataNormalizer()
        self._health: dict[str, SourceHealth] = {
            adapter.name: SourceHealth(source=adapter.name, priority=adapter.priority, enabled=adapter.enabled)
            for adapter in self.adapters
        }
        self._metric_failures: dict[tuple[str, str], int] = {}
        self._metric_open_until: dict[tuple[str, str], str] = {}
        self._audit_logger = _build_audit_logger()
        self._audit_events: list[dict[str, Any]] = []

    def fetch_realtime(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        return self._fetch(metric="realtime", symbol=symbol, **kwargs)

    def fetch_history(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        return self._fetch(metric="history", symbol=symbol, **kwargs)

    def fetch_news(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._fetch(metric="news", symbol=symbol, **kwargs)
        except DataUnavailableError:
            if not symbol:
                raise
            payload = self._fetch(metric="news", symbol=None, **kwargs)
            payload["symbol"] = symbol
            metadata = payload.setdefault("metadata", {})
            metadata["symbol_news_fallback"] = True
            return payload

    def fetch_flow(self, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._fetch(metric="flow", symbol=symbol, **kwargs)

    def get_source_health(self) -> list[dict[str, Any]]:
        """Expose source health for API and monitoring."""
        items = sorted(self._health.values(), key=lambda h: h.priority)
        payload = [item.to_dict() for item in items]
        cache_metrics = self.repository.get_cache_metrics()
        for item in payload:
            item["cache_metrics"] = cache_metrics
        return payload

    def get_recent_audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._audit_events[-limit:]

    def set_source_enabled(self, source_name: str, enabled: bool) -> None:
        """Enable/disable a source dynamically."""
        for adapter in self.adapters:
            if adapter.name == source_name:
                adapter.enabled = enabled
                self._health[source_name].enabled = enabled
                return
        raise ValueError(f"source not found: {source_name}")

    def _fetch(self, metric: str, symbol: str | None = None, **kwargs: Any) -> dict[str, Any]:
        bypass_cache = bool(kwargs.pop("bypass_cache", False))
        if not bypass_cache:
            cached = self.repository.get_cached(metric=metric, symbol=symbol)
            if cached is not None:
                metadata = dict(cached.get("metadata") or {})
                metadata["cache_hit"] = True
                cached["metadata"] = metadata
                cached["cache_metrics"] = self.repository.get_cache_metrics()
                return cached
        candidates = [a for a in self.adapters if a.enabled and a.supports(metric)]
        if not candidates:
            raise DataUnavailableError(f"no enabled source supports metric={metric}")
        local_kwargs = dict(kwargs)
        local_kwargs.setdefault("timeout_seconds", self.config.timeout_seconds)
        errors: list[str] = []
        failed_sources: list[str] = []
        for idx, adapter in enumerate(candidates):
            health = self._health[adapter.name]
            if self._is_circuit_open(health, metric):
                errors.append(f"{adapter.name}: circuit_open_until={health.circuit_open_until}")
                continue
            for attempt in range(self.config.retry_per_source + 1):
                started = time.perf_counter()
                try:
                    envelope = adapter.call_metric(metric=metric, symbol=symbol, **local_kwargs)
                    latency_ms = (time.perf_counter() - started) * 1000
                    self._mark_success(health, metric, latency_ms)
                    payload = self.normalizer.normalize(envelope.to_dict())
                    ttl = self.repository.set_cached(metric=metric, symbol=symbol, payload=payload)
                    self.repository.persist(payload)
                    payload["source_health"] = health.to_dict()
                    payload["cache_metrics"] = self.repository.get_cache_metrics()
                    metadata = dict(payload.get("metadata") or {})
                    metadata["cache_hit"] = False
                    metadata["cache_ttl_seconds"] = ttl
                    payload["metadata"] = metadata
                    if idx > 0:
                        self._record_switch_event(
                            metric=metric,
                            symbol=symbol,
                            selected=adapter.name,
                            failed_sources=failed_sources,
                            reason="; ".join(errors[-3:]),
                        )
                    return payload
                except Exception as exc:
                    latency_ms = (time.perf_counter() - started) * 1000
                    self._mark_failure(health, metric, str(exc), latency_ms)
                    errors.append(f"{adapter.name}[attempt={attempt + 1}]: {exc}")
            failed_sources.append(adapter.name)
        raise DataUnavailableError(
            f"all sources failed metric={metric}, symbol={symbol}, errors={errors}"
        )

    def _mark_success(self, health: SourceHealth, metric: str, latency_ms: float) -> None:
        key = (health.source, metric)
        health.success_count += 1
        health.consecutive_failures = 0
        health.last_error = None
        health.last_success_time = now_iso()
        self._metric_failures[key] = 0
        self._metric_open_until.pop(key, None)
        health.circuit_open_until = self._next_open_until_for_source(health.source)
        if health.avg_latency_ms is None:
            health.avg_latency_ms = latency_ms
        else:
            health.avg_latency_ms = health.avg_latency_ms * 0.7 + latency_ms * 0.3

    def _mark_failure(self, health: SourceHealth, metric: str, error: str, latency_ms: float) -> None:
        key = (health.source, metric)
        health.failure_count += 1
        metric_failures = self._metric_failures.get(key, 0) + 1
        self._metric_failures[key] = metric_failures
        health.consecutive_failures = metric_failures
        health.last_error = error
        health.last_failure_time = now_iso()
        if health.avg_latency_ms is None:
            health.avg_latency_ms = latency_ms
        else:
            health.avg_latency_ms = health.avg_latency_ms * 0.7 + latency_ms * 0.3
        if metric_failures >= self.config.failure_threshold:
            open_until = datetime.now(timezone.utc) + timedelta(seconds=self.config.cooldown_seconds)
            self._metric_open_until[key] = open_until.isoformat()
        health.circuit_open_until = self._next_open_until_for_source(health.source)

    def _is_circuit_open(self, health: SourceHealth, metric: str) -> bool:
        key = (health.source, metric)
        open_until_str = self._metric_open_until.get(key)
        if not open_until_str:
            return False
        try:
            open_until = datetime.fromisoformat(open_until_str)
        except ValueError:
            return False
        if datetime.now(timezone.utc) >= open_until:
            self._metric_open_until.pop(key, None)
            health.circuit_open_until = self._next_open_until_for_source(health.source)
            return False
        return True

    def _next_open_until_for_source(self, source: str) -> str | None:
        values = []
        for (name, _metric), open_until in self._metric_open_until.items():
            if name != source:
                continue
            values.append(open_until)
        return min(values) if values else None

    def _record_switch_event(
        self,
        metric: str,
        symbol: str | None,
        selected: str,
        failed_sources: list[str],
        reason: str,
    ) -> None:
        event = {
            "time": now_iso(),
            "metric": metric,
            "symbol": symbol,
            "selected_source": selected,
            "failed_sources": failed_sources,
            "reason": reason,
        }
        self._audit_events.append(event)
        if len(self._audit_events) > 500:
            self._audit_events = self._audit_events[-300:]
        self._audit_logger.warning(
            "source_switch metric=%s symbol=%s selected=%s failed=%s reason=%s",
            metric,
            symbol,
            selected,
            ",".join(failed_sources) if failed_sources else "-",
            reason,
        )


def _build_audit_logger() -> logging.Logger:
    logger = logging.getLogger("data_hub.audit")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    os.makedirs("logs", exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler("logs/data_hub_audit.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger
