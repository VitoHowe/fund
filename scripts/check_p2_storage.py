"""P2 validation: normalization, cache policy, and timeseries storage."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.data_hub import build_default_source_manager
from services.data_hub.exceptions import DataUnavailableError


def _shape_signature(payload: dict) -> list[str]:
    records = payload.get("records") or []
    if not records:
        return []
    keys = sorted(list(records[0].keys()))
    return keys


def main() -> None:
    manager = build_default_source_manager()
    symbol = "014943"
    report: dict[str, object] = {
        "symbol": symbol,
        "checks": {},
    }

    # 1) cache hit check
    first = manager.fetch_realtime(symbol)
    second = manager.fetch_realtime(symbol)
    report["checks"]["cache_hit_realtime"] = {
        "first_source": first.get("source"),
        "first_cache_hit": (first.get("metadata") or {}).get("cache_hit"),
        "second_source": second.get("source"),
        "second_cache_hit": (second.get("metadata") or {}).get("cache_hit"),
        "cache_metrics": second.get("cache_metrics"),
    }

    # 2) normalize consistency cross source
    history_main = manager.fetch_history(symbol, limit=3, bypass_cache=True)
    main_source = history_main.get("source")
    if main_source == "eastmoney":
        manager.set_source_enabled("eastmoney", False)
        history_backup = manager.fetch_history(symbol, limit=3, bypass_cache=True)
        manager.set_source_enabled("eastmoney", True)
    else:
        history_backup = history_main
    report["checks"]["cross_source_shape"] = {
        "main_source": main_source,
        "backup_source": history_backup.get("source"),
        "main_keys": _shape_signature(history_main),
        "backup_keys": _shape_signature(history_backup),
        "same_shape": _shape_signature(history_main) == _shape_signature(history_backup),
    }

    # 3) query timeseries response window
    now = datetime.now(tz=timezone.utc)
    start = (now - timedelta(days=30)).isoformat()
    end = now.isoformat()
    rows, elapsed_ms = manager.repository.query_history(
        metric="history",
        symbol=symbol,
        start_time_utc=start,
        end_time_utc=end,
        limit=200,
    )
    report["checks"]["timeseries_query"] = {
        "rows": len(rows),
        "elapsed_ms": elapsed_ms,
        "target_met_lt_500ms": elapsed_ms < 500,
        "sample": rows[0] if rows else None,
    }

    # 4) news fallback still alive
    try:
        news = manager.fetch_news(symbol=symbol, limit=10)
        report["checks"]["news_pipeline"] = {
            "ok": True,
            "source": news.get("source"),
            "rows": len(news.get("records") or []),
            "cache_hit": (news.get("metadata") or {}).get("cache_hit"),
        }
    except DataUnavailableError as exc:
        report["checks"]["news_pipeline"] = {"ok": False, "error": str(exc)}

    # 5) health + cache metrics
    report["checks"]["source_health"] = manager.get_source_health()
    report["checks"]["cache_metrics_final"] = manager.repository.get_cache_metrics()

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
