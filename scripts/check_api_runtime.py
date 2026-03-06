"""Smoke check for report API runtime endpoints."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def _fetch(path: str, timeout: int = 40) -> tuple[int, str]:
    with urlopen(f"http://127.0.0.1:8010{path}", timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(resp.status), body


def _fetch_with_retry(path: str, timeout: int, attempts: int, sleep_seconds: float = 1.2) -> tuple[int, str]:
    last_error: Exception | None = None
    for idx in range(attempts):
        try:
            return _fetch(path, timeout=timeout)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if idx < attempts - 1:
                time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("unexpected empty retry result")


def _wait_ready(max_seconds: int = 45) -> bool:
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            status, _ = _fetch("/health", timeout=5)
            if status == 200:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> None:
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "apps/api/report_api.py"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    output: dict[str, object] = {
        "checks": {},
        "endpoint_status": {},
    }
    ok = True
    try:
        ready = _wait_ready()
        output["checks"]["server_ready"] = ready
        if not ready:
            ok = False
            print(json.dumps(output, ensure_ascii=False, indent=2))
            raise SystemExit(1)

        endpoints = [
            "/health",
            "/api/monitor/data-sources",
            "/metrics",
            "/api/report/daily?symbols=014943,159870&market_state=neutral",
        ]
        for path in endpoints:
            try:
                if path.startswith("/api/report/daily"):
                    status, body = _fetch_with_retry(path, timeout=70, attempts=3)
                else:
                    status, body = _fetch_with_retry(path, timeout=20, attempts=2)
                output["endpoint_status"][path] = status
                if status != 200:
                    ok = False
                if path == "/metrics":
                    output["checks"]["metrics_enabled_present"] = "fund_data_source_enabled" in body
                    output["checks"]["metrics_alert_present"] = "fund_data_source_alert_total" in body
                if path.startswith("/api/report/daily"):
                    payload = json.loads(body)
                    output["checks"]["report_has_id"] = bool(payload.get("report_id"))
                    output["checks"]["report_has_summary"] = bool(payload.get("market_summary"))
                    output["checks"]["report_symbol_count_gt_0"] = (
                        int((payload.get("market_summary") or {}).get("symbol_count") or 0) > 0
                    )
            except (HTTPError, URLError, TimeoutError, ValueError) as exc:
                output["endpoint_status"][path] = f"error: {exc}"
                ok = False

        checks = output.get("checks", {})
        if isinstance(checks, dict):
            ok = ok and all(bool(v) for v in checks.values())

        print(json.dumps(output, ensure_ascii=False, indent=2))
        if not ok:
            raise SystemExit(1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr_tail = ""
        if proc.stderr:
            stderr_tail = "\n".join(proc.stderr.read().splitlines()[-12:])
        if stderr_tail:
            print("--- api stderr tail ---")
            print(stderr_tail)


if __name__ == "__main__":
    main()
