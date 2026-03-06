"""Unified repository: in-memory TTL cache + sqlite timeseries store."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from services.data_hub.cache_policy import CacheMetrics, CachePolicy


class DataRepository:
    """Repository for cache and persistent timeseries data."""

    def __init__(
        self,
        db_path: str = "data/fund_intel.db",
        schema_path: str = "infra/db/schema.sql",
        cache_policy: CachePolicy | None = None,
    ) -> None:
        self.db_path = db_path
        self.schema_path = schema_path
        self.cache_policy = cache_policy or CachePolicy()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_lock = threading.Lock()
        self._metrics = CacheMetrics()
        self._db_lock = threading.Lock()
        self._ensure_db()

    def get_cached(self, metric: str, symbol: str | None) -> dict[str, Any] | None:
        key = self._cache_key(metric, symbol)
        with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                self._metrics.misses += 1
                return None
            expires_at, payload = entry
            if time.time() > expires_at:
                self._cache.pop(key, None)
                self._metrics.expired += 1
                self._metrics.misses += 1
                return None
            self._metrics.hits += 1
            return json.loads(json.dumps(payload))

    def set_cached(self, metric: str, symbol: str | None, payload: dict[str, Any]) -> int:
        ttl = self.cache_policy.get_ttl_seconds(metric)
        key = self._cache_key(metric, symbol)
        expires_at = time.time() + ttl
        with self._cache_lock:
            self._cache[key] = (expires_at, json.loads(json.dumps(payload)))
            self._metrics.sets += 1
        return ttl

    def persist(self, payload: dict[str, Any]) -> None:
        rows = payload.get("records") or []
        if not isinstance(rows, list):
            return
        metric = payload.get("metric")
        symbol = payload.get("symbol")
        source = payload.get("source")
        source_time_utc = payload.get("source_time")
        ingest_time_utc = payload.get("ingest_time")
        quality_score = payload.get("quality_score")
        stale = 1 if payload.get("stale") else 0
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                for row in rows:
                    event_time_utc = row.get("event_time_utc")
                    conn.execute(
                        """
                        INSERT INTO timeseries_data(
                            metric, symbol, source, source_time_utc,
                            ingest_time_utc, event_time_utc, quality_score,
                            stale, record_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            metric,
                            symbol,
                            source,
                            source_time_utc,
                            ingest_time_utc,
                            event_time_utc,
                            quality_score,
                            stale,
                            json.dumps(row, ensure_ascii=False),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    def query_history(
        self,
        metric: str,
        symbol: str,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
        limit: int = 500,
    ) -> tuple[list[dict[str, Any]], float]:
        started = time.perf_counter()
        clauses = ["metric = ?", "symbol = ?"]
        params: list[Any] = [metric, symbol]
        if start_time_utc:
            clauses.append("event_time_utc >= ?")
            params.append(start_time_utc)
        if end_time_utc:
            clauses.append("event_time_utc <= ?")
            params.append(end_time_utc)
        where_sql = " AND ".join(clauses)
        sql = f"""
            SELECT metric, symbol, source, source_time_utc, ingest_time_utc, event_time_utc, quality_score, stale, record_json
            FROM timeseries_data
            WHERE {where_sql}
            ORDER BY event_time_utc DESC
            LIMIT ?
        """
        params.append(limit)
        rows: list[dict[str, Any]] = []
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute(sql, params)
                for item in cursor.fetchall():
                    rows.append(
                        {
                            "metric": item[0],
                            "symbol": item[1],
                            "source": item[2],
                            "source_time_utc": item[3],
                            "ingest_time_utc": item[4],
                            "event_time_utc": item[5],
                            "quality_score": item[6],
                            "stale": bool(item[7]),
                            "record": json.loads(item[8]),
                        }
                    )
            finally:
                conn.close()
        elapsed_ms = (time.perf_counter() - started) * 1000
        return rows, elapsed_ms

    def get_cache_metrics(self) -> dict[str, int]:
        with self._cache_lock:
            return self._metrics.to_dict()

    def _ensure_db(self) -> None:
        root = Path(__file__).resolve().parents[2]
        db_path = Path(self.db_path)
        if not db_path.is_absolute():
            db_path = root / db_path
            self.db_path = str(db_path)
        schema_file = Path(self.schema_path)
        if not schema_file.is_absolute():
            schema_file = root / schema_file
            self.schema_path = str(schema_file)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_text = Path(self.schema_path).read_text(encoding="utf-8")
        with self._db_lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.executescript(schema_text)
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _cache_key(metric: str, symbol: str | None) -> str:
        return f"{metric}:{symbol or 'market'}"
