"""Smoke check for report API runtime endpoints and admin console flows."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8010"
MOCK_URL = "http://127.0.0.1:8021"


class MockModelHandler(BaseHTTPRequestHandler):
    """Local OpenAI-compatible models endpoint for connectivity tests."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/v1/models":
            if self.headers.get("Authorization") != "Bearer test-key":
                self._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"data": [{"id": "mock-model"}, {"id": "mock-embedding"}]})
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _wait_ready(max_seconds: int = 60) -> bool:
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=5)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.5)
    return False


def _start_mock_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 8021), MockModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    mock_server = _start_mock_server()
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

        public_endpoints = [
            "/health",
            "/api/monitor/data-sources",
            "/metrics",
            "/api/report/daily?symbols=014943,159870&market_state=neutral",
        ]
        for path in public_endpoints:
            resp = requests.get(f"{BASE_URL}{path}", timeout=90)
            output["endpoint_status"][path] = resp.status_code
            if resp.status_code != 200:
                ok = False
                continue
            if path == "/metrics":
                body = resp.text
                output["checks"]["metrics_enabled_present"] = "fund_data_source_enabled" in body
                output["checks"]["metrics_alert_present"] = "fund_data_source_alert_total" in body
            if path.startswith("/api/report/daily"):
                payload = resp.json()
                output["checks"]["report_has_id"] = bool(payload.get("report_id"))
                output["checks"]["report_has_summary"] = bool(payload.get("market_summary"))
                output["checks"]["report_symbol_count_gt_0"] = (
                    int((payload.get("market_summary") or {}).get("symbol_count") or 0) > 0
                )

        session = requests.Session()
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={"password": "fund-admin"}, timeout=10)
        output["endpoint_status"]["/api/auth/login"] = login_resp.status_code
        output["checks"]["login_ok"] = login_resp.status_code == 200 and login_resp.json().get("authenticated") is True
        ok = ok and output["checks"]["login_ok"]

        session_resp = session.get(f"{BASE_URL}/api/auth/session", timeout=10)
        output["endpoint_status"]["/api/auth/session"] = session_resp.status_code
        session_payload = session_resp.json()
        output["checks"]["session_authenticated"] = bool(session_payload.get("authenticated"))
        output["checks"]["runtime_versions_present"] = bool(session_payload.get("config_versions"))

        dashboard_resp = session.get(f"{BASE_URL}/dashboard/today", timeout=10)
        output["endpoint_status"]["/dashboard/today"] = dashboard_resp.status_code
        output["checks"]["dashboard_page_available"] = (
            dashboard_resp.status_code == 200 and "Fund Intel Admin" in dashboard_resp.text
        )

        asset_resp = session.get(f"{BASE_URL}/assets/app.js", timeout=10)
        output["endpoint_status"]["/assets/app.js"] = asset_resp.status_code
        output["checks"]["asset_page_available"] = asset_resp.status_code == 200 and "renderDashboard" in asset_resp.text

        model_payload = {
            "id": "mock-openai",
            "name": "Mock OpenAI",
            "url": f"{MOCK_URL}/v1",
            "apiKey": "test-key",
            "model": "mock-model",
            "enabled": True,
            "is_default": True,
        }
        existing_models_resp = session.get(f"{BASE_URL}/api/settings/models", timeout=10)
        existing_models = existing_models_resp.json()
        existing_model = next(
            (item for item in existing_models.get("items") or [] if item.get("id") == "mock-openai"),
            None,
        )
        if existing_model:
            model_create_resp = session.put(
                f"{BASE_URL}/api/settings/models/mock-openai",
                json=model_payload,
                timeout=10,
            )
        else:
            model_create_resp = session.post(
                f"{BASE_URL}/api/settings/models",
                json=model_payload,
                timeout=10,
            )
        output["endpoint_status"]["/api/settings/models"] = model_create_resp.status_code
        model_list_resp = session.get(f"{BASE_URL}/api/settings/models", timeout=10)
        models_payload = model_list_resp.json()
        model_item = next((item for item in models_payload.get("items") or [] if item.get("id") == "mock-openai"), {})
        output["checks"]["model_config_present"] = bool(model_item)
        output["checks"]["model_api_key_masked"] = "*" in str(model_item.get("apiKey") or "")

        model_test_resp = session.post(f"{BASE_URL}/api/settings/models/mock-openai/test", json={}, timeout=10)
        output["endpoint_status"]["/api/settings/models/mock-openai/test"] = model_test_resp.status_code
        model_test_payload = model_test_resp.json()
        output["checks"]["model_test_ok"] = bool(model_test_payload.get("ok"))
        output["checks"]["model_test_connectivity"] = bool((model_test_payload.get("connectivity") or {}).get("ok"))

        strategies_resp = session.get(f"{BASE_URL}/api/settings/strategies", timeout=10)
        output["endpoint_status"]["/api/settings/strategies"] = strategies_resp.status_code
        strategies_payload = strategies_resp.json()
        default_strategy = next(
            (item for item in strategies_payload.get("items") or [] if item.get("is_default")),
            (strategies_payload.get("items") or [None])[0],
        )
        strategy_id = default_strategy.get("id") if default_strategy else ""
        output["checks"]["strategy_present"] = bool(strategy_id)

        tune_resp = session.post(
            f"{BASE_URL}/api/settings/strategies/{strategy_id}/replay-tune",
            json={"symbols": "014943", "market_state": "neutral", "limit": 60, "persist": True},
            timeout=180,
        )
        output["endpoint_status"]["/api/settings/strategies/{id}/replay-tune"] = tune_resp.status_code
        tune_payload = tune_resp.json()
        output["checks"]["strategy_tune_has_ranking"] = bool(tune_payload.get("ranking"))
        output["checks"]["strategy_tune_persisted"] = bool(tune_payload.get("persisted"))

        runtime_resp = session.get(f"{BASE_URL}/api/settings/runtime", timeout=10)
        output["endpoint_status"]["/api/settings/runtime"] = runtime_resp.status_code
        output["checks"]["runtime_endpoint_ok"] = runtime_resp.status_code == 200

        latest_resp = session.get(f"{BASE_URL}/api/report/daily/latest", timeout=10)
        output["endpoint_status"]["/api/report/daily/latest"] = latest_resp.status_code
        latest_payload = latest_resp.json()
        output["checks"]["latest_report_available"] = bool(latest_payload.get("report_id"))

        logout_resp = session.post(f"{BASE_URL}/api/auth/logout", json={}, timeout=10)
        output["endpoint_status"]["/api/auth/logout"] = logout_resp.status_code
        output["checks"]["logout_ok"] = logout_resp.status_code == 200

        checks = output.get("checks", {})
        if isinstance(checks, dict):
            ok = ok and all(bool(v) for v in checks.values())

        print(json.dumps(output, ensure_ascii=False, indent=2))
        if not ok:
            raise SystemExit(1)
    finally:
        mock_server.shutdown()
        mock_server.server_close()
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr_tail = ""
        if proc.stderr:
            stderr_tail = "\n".join(proc.stderr.read().splitlines()[-20:])
        if stderr_tail:
            print("--- api stderr tail ---")
            print(stderr_tail)


if __name__ == "__main__":
    main()
