"""Run live integration checks for the four required fund endpoints."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8010"
TARGETS = (
    "/api/report/fund-detail?symbol=017193",
    "/api/report/fund-detail?symbol=011452",
    "/api/report/daily?symbols=017193,011452&market_state=neutral",
    "/api/monitor/data-sources",
)


def _wait_ready(max_seconds: int = 90) -> bool:
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.5)
    return False


def _summarize_pipeline(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for row in rows or []:
        summary.append(
            {
                "source": row.get("source"),
                "status": row.get("status"),
                "route_state": row.get("route_state"),
                "fallback_source": row.get("fallback_source"),
                "error_type": row.get("error_type"),
                "error_message": row.get("error_message"),
                "metrics": row.get("metrics"),
            }
        )
    return summary


def _summarize_detail(payload: dict[str, Any]) -> dict[str, Any]:
    detail = payload.get("detail") or {}
    return {
        "symbol": payload.get("symbol"),
        "name": detail.get("name"),
        "tactical_action": detail.get("tactical_action"),
        "tactical_reason": detail.get("tactical_reason"),
        "risk_tags": detail.get("risk_tags"),
        "source_time_utc": detail.get("source_time_utc"),
        "backtest_status": (detail.get("backtest_summary") or {}).get("status"),
        "quality_score": payload.get("quality_score"),
        "data_pipeline": _summarize_pipeline(payload.get("data_pipeline")),
    }


def _summarize_daily(payload: dict[str, Any]) -> dict[str, Any]:
    ranking = payload.get("ranking") or []
    return {
        "report_id": payload.get("report_id"),
        "quality_score": payload.get("quality_score"),
        "market_summary": payload.get("market_summary"),
        "risk_alerts": payload.get("risk_alerts"),
        "ranking": [
            {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "tactical_action": row.get("tactical_action"),
                "total_score": row.get("total_score"),
            }
            for row in ranking[:5]
        ],
        "data_pipeline": _summarize_pipeline(payload.get("data_pipeline")),
    }


def _summarize_monitor(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_status": payload.get("overall_status"),
        "state_counts": payload.get("state_counts"),
        "alerts": payload.get("alerts"),
        "sources": [
            {
                "source": row.get("source"),
                "status": row.get("status"),
                "route_state": row.get("route_state"),
                "last_metric": row.get("last_metric"),
                "error_type": row.get("error_type"),
                "error_message": row.get("error_message"),
                "fallback_source": row.get("fallback_source"),
                "supported_metrics": row.get("supported_metrics"),
            }
            for row in payload.get("sources") or []
        ],
    }


def main() -> None:
    process = subprocess.Popen(
        [sys.executable, "apps/api/report_api.py"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    output: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "endpoints": {},
    }
    try:
        if not _wait_ready():
            output["error"] = "server_not_ready"
            print(json.dumps(output, ensure_ascii=False, indent=2))
            raise SystemExit(1)
        for path in TARGETS:
            response = requests.get(f"{BASE_URL}{path}", timeout=180)
            entry: dict[str, Any] = {"status_code": response.status_code}
            if response.status_code == 200:
                payload = response.json()
                if path.startswith("/api/report/fund-detail"):
                    entry["summary"] = _summarize_detail(payload)
                elif path.startswith("/api/report/daily"):
                    entry["summary"] = _summarize_daily(payload)
                else:
                    entry["summary"] = _summarize_monitor(payload)
            else:
                entry["body"] = response.text[:1000]
            output["endpoints"][path] = entry
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    main()
