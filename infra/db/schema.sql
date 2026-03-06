-- P2 storage schema
-- Time fields are stored in UTC ISO8601 strings.

CREATE TABLE IF NOT EXISTS timeseries_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric TEXT NOT NULL,
    symbol TEXT NOT NULL,
    source TEXT NOT NULL,
    source_time_utc TEXT,
    ingest_time_utc TEXT NOT NULL,
    event_time_utc TEXT,
    quality_score REAL,
    stale INTEGER NOT NULL DEFAULT 0,
    record_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timeseries_metric_symbol_event
    ON timeseries_data(metric, symbol, event_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_timeseries_ingest_time
    ON timeseries_data(ingest_time_utc DESC);

CREATE TABLE IF NOT EXISTS source_health_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    success_count INTEGER NOT NULL,
    failure_count INTEGER NOT NULL,
    circuit_open_until TEXT,
    captured_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_health_source_metric_time
    ON source_health_snapshot(source, metric, captured_at_utc DESC);

