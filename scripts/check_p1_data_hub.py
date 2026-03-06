"""P1 validation script for data hub routing and health."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the script runnable without manual PYTHONPATH setup.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.data_hub import build_default_source_manager
from services.data_hub.exceptions import DataUnavailableError


def main() -> None:
    manager = build_default_source_manager()
    target_fund = "014943"

    report: dict[str, object] = {
        "target_fund": target_fund,
        "checks": {},
        "health_before": manager.get_source_health(),
    }

    try:
        realtime = manager.fetch_realtime(target_fund)
        report["checks"]["realtime"] = {
            "ok": True,
            "source": realtime["source"],
            "source_time": realtime.get("source_time"),
            "sample": (realtime.get("records") or [None])[0],
        }
    except Exception as exc:  # pragma: no cover
        report["checks"]["realtime"] = {"ok": False, "error": str(exc)}

    try:
        history = manager.fetch_history(target_fund, limit=5, bypass_cache=True)
        report["checks"]["history"] = {
            "ok": True,
            "source": history["source"],
            "source_time": history.get("source_time"),
            "rows": len(history.get("records") or []),
            "sample": (history.get("records") or [None])[0],
        }
    except Exception as exc:  # pragma: no cover
        report["checks"]["history"] = {"ok": False, "error": str(exc)}

    try:
        news = manager.fetch_news(symbol=target_fund, limit=10)
        report["checks"]["news"] = {
            "ok": True,
            "source": news["source"],
            "rows": len(news.get("records") or []),
            "sample": (news.get("records") or [None])[0],
        }
    except Exception as exc:  # pragma: no cover
        report["checks"]["news"] = {"ok": False, "error": str(exc)}

    # Simulate primary source failure and verify fallback.
    eastmoney = next(a for a in manager.adapters if a.name == "eastmoney")
    original_fetch_history = eastmoney.fetch_history
    fallback_report: dict[str, object] = {"ok": False}
    try:
        def forced_failure(symbol: str, **kwargs):  # type: ignore[no-untyped-def]
            raise DataUnavailableError("forced eastmoney history failure for fallback test")

        eastmoney.fetch_history = forced_failure  # type: ignore[assignment]
        fallback_result = manager.fetch_history(target_fund, limit=3, bypass_cache=True)
        fallback_report = {
            "ok": True,
            "fallback_source": fallback_result["source"],
            "rows": len(fallback_result.get("records") or []),
            "sample": (fallback_result.get("records") or [None])[0],
        }
    except Exception as exc:  # pragma: no cover
        fallback_report = {"ok": False, "error": str(exc)}
    finally:
        eastmoney.fetch_history = original_fetch_history
    report["checks"]["fallback_history"] = fallback_report

    report["health_after"] = manager.get_source_health()
    report["audit_events"] = manager.get_recent_audit_events(limit=20)

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
