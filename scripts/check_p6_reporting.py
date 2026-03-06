"""P6 validation: report system and dashboard assets."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.backtest import BacktestRunner
from services.data_hub import build_default_source_manager
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry
from services.news_pipeline import NewsFusionService
from services.reporting import DailyReportOptions, DailyReportService


def main() -> None:
    source_manager = build_default_source_manager()
    scorer = FactorScorer(
        source_manager=source_manager,
        registry=build_default_factor_registry(),
        weight_manager=WeightTemplateManager(config_path=str(ROOT / "config" / "factor_weights.yaml")),
    )
    news_service = NewsFusionService()
    backtest_runner = BacktestRunner(source_manager=source_manager, factor_scorer=scorer)
    service = DailyReportService(
        source_manager=source_manager,
        factor_scorer=scorer,
        news_service=news_service,
        backtest_runner=backtest_runner,
    )
    report = service.generate_daily_report(
        symbols=["014943", "159870"],
        proxy_symbol_map={"014943": "159870"},
        options=DailyReportOptions(market_state="neutral", include_backtest=True),
    )
    payload = report.to_dict()
    assert len(payload.get("ranking") or []) >= 1, "ranking should not be empty"
    assert len(payload.get("fund_details") or []) >= 1, "fund details should not be empty"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        md_path = tmp / "daily.md"
        html_path = tmp / "daily.html"
        pdf_path = tmp / "daily.pdf"
        md_bytes = service.export_report(report, fmt="md")
        html_bytes = service.export_report(report, fmt="html")
        pdf_bytes = service.export_report(report, fmt="pdf")
        md_path.write_bytes(md_bytes)
        html_path.write_bytes(html_bytes)
        pdf_path.write_bytes(pdf_bytes)
        md_text = md_path.read_text(encoding="utf-8")
        html_text = html_path.read_text(encoding="utf-8")
        report_id = report.report_id
        assert report_id in md_text and report_id in html_text, "report id should appear in exports"
        assert "分级榜单" in md_text and "分级榜单" in html_text, "ranking section should be present"
        assert pdf_path.stat().st_size > 200, "pdf export should be non-empty"

    etf_page = ROOT / "apps" / "web" / "src" / "pages" / "etf-report.tsx"
    detail_page = ROOT / "apps" / "web" / "src" / "pages" / "fund-detail.tsx"
    assert etf_page.exists() and detail_page.exists(), "frontend pages should exist"
    output = {
        "checks": {
            "daily_report_generated": True,
            "ranking_present": len(payload.get("ranking") or []) > 0,
            "fund_details_present": len(payload.get("fund_details") or []) > 0,
            "export_markdown_html_pdf": True,
            "export_content_consistent": True,
            "frontend_pages_present": True,
        },
        "report_id": report.report_id,
        "report_date": report.report_date,
        "summary": {
            "symbol_count": payload.get("market_summary", {}).get("symbol_count"),
            "avg_score": payload.get("market_summary", {}).get("avg_score"),
            "risk_alert_count": len(payload.get("risk_alerts") or []),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

