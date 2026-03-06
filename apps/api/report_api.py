"""Minimal HTTP API for daily report and fund detail."""

from __future__ import annotations

import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Allow running as `python apps/api/report_api.py` from repo root without extra PYTHONPATH setup.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.backtest import BacktestRunner
from services.data_hub import build_default_source_manager
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry
from services.news_pipeline import NewsFusionService
from services.observability import SourceMonitor
from services.reporting import DailyReportOptions, DailyReportService


def build_runtime() -> tuple[DailyReportService, SourceMonitor]:
    source_manager = build_default_source_manager()
    factor_scorer = FactorScorer(
        source_manager=source_manager,
        registry=build_default_factor_registry(),
        weight_manager=WeightTemplateManager(config_path="config/factor_weights.yaml"),
    )
    news_service = NewsFusionService()
    backtest_runner = BacktestRunner(source_manager=source_manager, factor_scorer=factor_scorer)
    service = DailyReportService(
        source_manager=source_manager,
        factor_scorer=factor_scorer,
        news_service=news_service,
        backtest_runner=backtest_runner,
    )
    monitor = SourceMonitor(source_manager=source_manager)
    return service, monitor


class ReportApiHandler(BaseHTTPRequestHandler):
    service: DailyReportService
    monitor: SourceMonitor
    service, monitor = build_runtime()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)
        try:
            if path == "/health":
                self._send_json({"status": "ok", "service": "report_api"})
                return
            if path == "/api/monitor/data-sources":
                self._send_json(self.monitor.snapshot())
                return
            if path == "/metrics":
                data = self.monitor.prometheus_text().encode("utf-8")
                self._send_bytes(data=data, content_type="text/plain; version=0.0.4; charset=utf-8")
                return
            if path == "/api/report/daily":
                report = self._generate_report(qs)
                self._send_json(report)
                return
            if path == "/api/report/fund-detail":
                symbol = (qs.get("symbol") or ["014943"])[0]
                report = self._generate_report({"symbols": [symbol]})
                detail = (report.get("fund_details") or [None])[0]
                self._send_json({"symbol": symbol, "detail": detail, "report_id": report.get("report_id")})
                return
            if path == "/api/report/export":
                fmt = ((qs.get("format") or ["md"])[0]).lower()
                report_obj = self.service.generate_daily_report(
                    symbols=self._parse_symbols(qs),
                    proxy_symbol_map={"014943": "159870"},
                    options=DailyReportOptions(market_state=(qs.get("market_state") or ["neutral"])[0]),
                )
                data = self.service.export_report(report_obj, fmt=fmt)
                ctype = {
                    "md": "text/markdown; charset=utf-8",
                    "html": "text/html; charset=utf-8",
                    "pdf": "application/pdf",
                }.get(fmt, "application/octet-stream")
                filename = f"{report_obj.report_id}.{fmt}"
                self._send_bytes(data=data, content_type=ctype, filename=filename)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")
        except Exception as exc:  # pragma: no cover
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _generate_report(self, qs: dict[str, list[str]]) -> dict:
        symbols = self._parse_symbols(qs)
        market_state = (qs.get("market_state") or ["neutral"])[0]
        report = self.service.generate_daily_report(
            symbols=symbols,
            proxy_symbol_map={"014943": "159870"},
            options=DailyReportOptions(market_state=market_state),
        )
        return report.to_dict()

    @staticmethod
    def _parse_symbols(qs: dict[str, list[str]]) -> list[str]:
        raw = (qs.get("symbols") or ["014943,159870"])[0]
        values = [item.strip() for item in raw.split(",") if item.strip()]
        return values or ["014943"]

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(host: str = "127.0.0.1", port: int = 8010) -> None:
    server = ThreadingHTTPServer((host, port), ReportApiHandler)
    print(f"Report API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
