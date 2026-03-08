"""Source manager with fallback, retries, tracing and circuit breaker support."""

from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.data_hub.adapters.base import IDataSourceAdapter
from services.data_hub.cache_policy import CachePolicy
from services.data_hub.exceptions import (
    AdapterNotSupportedError,
    DataProtocolError,
    DataSourceError,
    DataTimeoutError,
    DataTransportError,
    DataUnavailableError,
    DataUpstreamError,
    DataValidationError,
)
from services.data_hub.normalizer import DataNormalizer
from services.data_hub.repository import DataRepository
from services.data_hub.types import SourceHealth, now_iso

TRACE_CONTEXT: ContextVar[tuple[str, ...]] = ContextVar("fund_source_trace_ids", default=())


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
            adapter.name: SourceHealth(
                source=adapter.name,
                priority=adapter.priority,
                supported_metrics=list(adapter.supported_metrics),
                enabled=adapter.enabled,
            )
            for adapter in self.adapters
        }
        self._metric_failures: dict[tuple[str, str], int] = {}
        self._metric_open_until: dict[tuple[str, str], str] = {}
        self._audit_logger = _build_audit_logger()
        self._audit_events: list[dict[str, Any]] = []
        self._trace_lock = threading.RLock()
        self._request_traces: dict[str, list[dict[str, Any]]] = {}

    def begin_trace(self, label: str | None = None) -> tuple[str, Any]:
        trace_id = f"trace-{int(time.time() * 1000)}-{secrets.token_hex(4)}"
        with self._trace_lock:
            self._request_traces[trace_id] = []
            if label:
                self._request_traces[trace_id].append(
                    {
                        "time": now_iso(),
                        "type": "trace_start",
                        "trace_id": trace_id,
                        "label": label,
                    }
                )
        current = TRACE_CONTEXT.get()
        token = TRACE_CONTEXT.set(current + (trace_id,))
        return trace_id, token

    def end_trace(self, handle: tuple[str, Any] | None) -> list[dict[str, Any]]:
        if handle is None:
            return []
        trace_id, token = handle
        try:
            TRACE_CONTEXT.reset(token)
        except Exception:
            pass
        with self._trace_lock:
            return list(self._request_traces.pop(trace_id, []))

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
            item["route_state"] = _route_state(item)
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
        stable_only = bool(kwargs.pop("stable_only", False))
        if not bypass_cache:
            cached = self.repository.get_cached(metric=metric, symbol=symbol)
            if cached is not None:
                metadata = dict(cached.get("metadata") or {})
                metadata["cache_hit"] = True
                cached["metadata"] = metadata
                cached["cache_metrics"] = self.repository.get_cache_metrics()
                source_name = str(cached.get("source") or "")
                if source_name in self._health:
                    self._mark_cached(
                        self._health[source_name],
                        metric=metric,
                        quality_score=_to_float_or_none(cached.get("quality_score")),
                    )
                self._record_trace_event(
                    {
                        "time": now_iso(),
                        "metric": metric,
                        "symbol": symbol,
                        "source": source_name or "cache",
                        "status": "fallback_cache",
                        "latency_ms": 0.0,
                        "fallback_source": "cache",
                        "quality_score": _to_float_or_none(cached.get("quality_score")),
                        "error_message": None,
                        "cache_hit": True,
                    }
                )
                return cached
        candidates = [a for a in self.adapters if a.enabled and a.supports(metric)]
        if stable_only:
            stable_candidates = [adapter for adapter in candidates if self._is_candidate_stable(adapter.name)]
            if stable_candidates:
                candidates = stable_candidates
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
            skip_adapter = False
            for attempt in range(self.config.retry_per_source + 1):
                started = time.perf_counter()
                try:
                    envelope = adapter.call_metric(metric=metric, symbol=symbol, **local_kwargs)
                    latency_ms = (time.perf_counter() - started) * 1000
                    payload = self.normalizer.normalize(envelope.to_dict())
                    quality_score = _to_float_or_none(payload.get("quality_score"))
                    self._mark_success(
                        health,
                        metric=metric,
                        latency_ms=latency_ms,
                        quality_score=quality_score,
                        partial=bool(failed_sources),
                    )
                    ttl = self.repository.set_cached(metric=metric, symbol=symbol, payload=payload)
                    self.repository.persist(payload)
                    payload["source_health"] = health.to_dict()
                    payload["cache_metrics"] = self.repository.get_cache_metrics()
                    metadata = dict(payload.get("metadata") or {})
                    metadata["cache_hit"] = False
                    metadata["cache_ttl_seconds"] = ttl
                    metadata["failed_sources"] = list(failed_sources)
                    payload["metadata"] = metadata
                    if failed_sources:
                        for failed_name in failed_sources:
                            self._attach_fallback_source(failed_name, adapter.name)
                    self._record_trace_event(
                        {
                            "time": now_iso(),
                            "metric": metric,
                            "symbol": symbol,
                            "source": adapter.name,
                            "status": "partial_success" if failed_sources else "success",
                            "latency_ms": round(latency_ms, 2),
                            "fallback_source": None,
                            "quality_score": quality_score,
                            "error_message": None,
                            "failed_sources": list(failed_sources),
                            "cache_hit": False,
                        }
                    )
                    if idx > 0:
                        self._record_switch_event(
                            metric=metric,
                            symbol=symbol,
                            selected=adapter.name,
                            failed_sources=failed_sources,
                            reason="; ".join(errors[-3:]),
                        )
                    return payload
                except AdapterNotSupportedError as exc:
                    errors.append(f"{adapter.name}[attempt={attempt + 1}]: skipped={exc}")
                    skip_adapter = True
                    break
                except Exception as exc:
                    latency_ms = (time.perf_counter() - started) * 1000
                    error_type = _classify_error(exc)
                    self._mark_failure(health, metric, str(exc), latency_ms, error_type=error_type)
                    self._record_trace_event(
                        {
                            "time": now_iso(),
                            "metric": metric,
                            "symbol": symbol,
                            "source": adapter.name,
                            "status": "failed",
                            "latency_ms": round(latency_ms, 2),
                            "fallback_source": None,
                            "quality_score": None,
                            "error_message": str(exc),
                            "error_type": error_type,
                            "cache_hit": False,
                        }
                    )
                    errors.append(f"{adapter.name}[attempt={attempt + 1}]: {exc}")
            if not skip_adapter:
                failed_sources.append(adapter.name)
        raise DataUnavailableError(f"all sources failed metric={metric}, symbol={symbol}, errors={errors}")

    def _mark_success(
        self,
        health: SourceHealth,
        metric: str,
        latency_ms: float,
        *,
        quality_score: float | None,
        partial: bool,
    ) -> None:
        key = (health.source, metric)
        health.success_count += 1
        health.consecutive_failures = 0
        health.last_error = None
        health.last_success_time = now_iso()
        health.last_metric = metric
        health.status = "partial_success" if partial else "success"
        health.route_state = "degraded" if partial else "ok"
        health.latency_ms = round(latency_ms, 2)
        health.quality_score = quality_score
        health.error_message = None
        health.error_type = None
        if not partial:
            health.fallback_source = None
        self._metric_failures[key] = 0
        self._metric_open_until.pop(key, None)
        health.circuit_open_until = self._next_open_until_for_source(health.source)
        if health.avg_latency_ms is None:
            health.avg_latency_ms = latency_ms
        else:
            health.avg_latency_ms = health.avg_latency_ms * 0.7 + latency_ms * 0.3

    def _mark_cached(self, health: SourceHealth, metric: str, quality_score: float | None) -> None:
        health.last_metric = metric
        health.status = "fallback_cache"
        health.route_state = "degraded"
        health.latency_ms = 0.0
        health.quality_score = quality_score
        health.fallback_source = "cache"
        health.error_message = None
        health.error_type = None

    def _mark_failure(
        self,
        health: SourceHealth,
        metric: str,
        error: str,
        latency_ms: float,
        *,
        error_type: str,
    ) -> None:
        key = (health.source, metric)
        health.failure_count += 1
        metric_failures = self._metric_failures.get(key, 0) + 1
        self._metric_failures[key] = metric_failures
        health.consecutive_failures = metric_failures
        health.last_metric = metric
        health.last_error = error
        health.last_failure_time = now_iso()
        health.status = "failed"
        health.route_state = "unavailable"
        health.latency_ms = round(latency_ms, 2)
        health.error_message = error
        health.error_type = error_type
        health.quality_score = None
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

    def _attach_fallback_source(self, source_name: str, fallback_source: str) -> None:
        health = self._health.get(source_name)
        if not health:
            return
        health.fallback_source = fallback_source
        if health.status == "failed":
            health.route_state = "degraded"

    def _is_candidate_stable(self, source_name: str) -> bool:
        health = self._health.get(source_name)
        if health is None:
            return True
        return bool(
            health.enabled
            and health.consecutive_failures == 0
            and not health.circuit_open_until
            and (health.status != "failed" or health.success_count == 0)
        )

    def _record_trace_event(self, event: dict[str, Any]) -> None:
        trace_ids = TRACE_CONTEXT.get()
        if not trace_ids:
            return
        with self._trace_lock:
            for trace_id in trace_ids:
                bucket = self._request_traces.get(trace_id)
                if bucket is None:
                    continue
                bucket.append(dict(event))

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


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, DataTimeoutError):
        return "timeout"
    if isinstance(exc, (DataTransportError, ConnectionError)):
        return "transport"
    if isinstance(exc, DataUpstreamError):
        return "upstream"
    if isinstance(exc, DataValidationError):
        return "validation"
    if isinstance(exc, DataProtocolError):
        return "protocol"
    if isinstance(exc, DataUnavailableError):
        return "unavailable"
    if isinstance(exc, DataSourceError):
        return "source"
    return "unknown"


def _route_state(item: dict[str, Any]) -> str:
    if not item.get("enabled", True):
        return "disabled"
    status = str(item.get("status") or "not_requested")
    if status == "success":
        return "ok"
    if status in {"partial_success", "fallback_cache"}:
        return "degraded"
    if status == "failed":
        if item.get("fallback_source"):
            return "degraded"
        return "unavailable"
    return "idle"
