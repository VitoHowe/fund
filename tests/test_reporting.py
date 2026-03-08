"""Unit tests for report template and service."""

from __future__ import annotations

import unittest

from services.reporting.daily_report_service import DailyReportOptions, DailyReportService
from services.reporting.template_engine import ReportTemplateEngine


class _ScoreCard:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class FakeFactorScorer:
    def score_symbol(self, symbol, market_state="neutral", proxy_symbol=None, extra_context=None):
        sentiment_raw = ((extra_context or {}).get("news_feature") or {})
        return _ScoreCard(
            {
                "symbol": symbol,
                "total_score": 66.0 if symbol == "014943" else 58.0,
                "confidence": 0.77,
                "risk_tags": ["FLOW_PROXY_SYMBOL"] if symbol == "014943" else [],
                "factor_scores": {
                    "sentiment": {
                        "source_refs": ["news_pipeline:feature_summary"],
                        "raw": {"latest_news_time_utc": sentiment_raw.get("latest_news_time_utc")},
                    }
                },
            }
        )


class FakeNewsSummary:
    def __init__(self, symbol):
        self.symbol = symbol
        self.rows = 1
        self.avg_sentiment = 0.6
        self.positive_ratio = 1.0
        self.negative_ratio = 0.0
        self.credibility_weighted_sentiment = 0.8
        self.latest_news_time_utc = "2026-03-06T00:00:00+00:00"
        self.tags = ["NEWS_BULLISH"]

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "rows": self.rows,
            "avg_sentiment": self.avg_sentiment,
            "positive_ratio": self.positive_ratio,
            "negative_ratio": self.negative_ratio,
            "credibility_weighted_sentiment": self.credibility_weighted_sentiment,
            "latest_news_time_utc": self.latest_news_time_utc,
            "tags": self.tags,
        }


class FakeNewsService:
    def collect_items(self, limit=50, tavily_query=None):
        return [], {"eastmoney": 0, "tavily": 0}, 0

    def symbol_news(self, symbol, items):
        return []

    def build_factor_extra(self, symbol, items, source_options=None):
        return {"news_feature": FakeNewsSummary(symbol).to_dict()}


class FakeBacktestRunner:
    def run(self, symbol, strategies, market_state="neutral", proxy_symbol=None, limit=120, config=None):
        return {
            "snapshot_hash": f"hash-{symbol}",
            "ranking": [
                {"strategy": "score_threshold", "total_return_pct": 1.2, "max_drawdown_pct": -1.1, "sharpe": 0.8}
            ],
        }


class FakeSourceManager:
    def fetch_realtime(self, symbol, **kwargs):
        return {"records": [{"name": f"name-{symbol}"}]}

    def fetch_flow(self, symbol=None, **kwargs):
        return {
            "records": [
                {
                    "sector": "化工",
                    "change_pct": 1.2,
                    "main_net_inflow": 10000.0,
                    "main_inflow_ratio": 0.8,
                    "top_stock": "159870",
                }
            ]
        }


class FailingFlowSourceManager(FakeSourceManager):
    def fetch_flow(self, symbol=None, **kwargs):
        raise RuntimeError("simulated flow failure")


class GuardrailFactorScorer:
    def score_symbol(self, symbol, market_state="neutral", proxy_symbol=None, extra_context=None):
        return _ScoreCard(
            {
                "symbol": symbol,
                "total_score": 81.0,
                "confidence": 0.88,
                "risk_tags": ["FLOW_DATA_UNAVAILABLE", "NEWS_DATA_UNAVAILABLE"],
                "factor_scores": {
                    "flow": {
                        "score": 50.0,
                        "confidence": 0.2,
                        "weight": 0.2,
                        "contribution": 10.0,
                        "raw": {"error": "flow unavailable"},
                        "source_refs": [],
                    },
                    "sentiment": {
                        "score": 50.0,
                        "confidence": 0.2,
                        "weight": 0.2,
                        "contribution": 10.0,
                        "raw": {"error": "news unavailable"},
                        "source_refs": [],
                    },
                },
            }
        )


class FailingBacktestRunner:
    def run(self, symbol, strategies, market_state="neutral", proxy_symbol=None, limit=120, config=None, stable_only=False):
        raise ValueError("history snapshot is not enough for backtest")


class ReportingTests(unittest.TestCase):
    def test_report_generation_and_export(self):
        service = DailyReportService(
            source_manager=FakeSourceManager(),
            factor_scorer=FakeFactorScorer(),
            news_service=FakeNewsService(),
            backtest_runner=FakeBacktestRunner(),
        )
        report = service.generate_daily_report(
            symbols=["014943", "159870"],
            proxy_symbol_map={"014943": "159870"},
            options=DailyReportOptions(include_backtest=True),
        )
        payload = report.to_dict()
        self.assertGreaterEqual(len(payload["ranking"]), 2)
        self.assertGreaterEqual(len(payload["fund_details"]), 2)
        md = service.export_report(report, "md").decode("utf-8")
        html = service.export_report(report, "html").decode("utf-8")
        pdf = service.export_report(report, "pdf")
        self.assertIn(report.report_id, md)
        self.assertIn(report.report_id, html)
        self.assertGreater(len(pdf), 200)

    def test_template_engine_sections(self):
        service = DailyReportService(
            source_manager=FakeSourceManager(),
            factor_scorer=FakeFactorScorer(),
            news_service=FakeNewsService(),
            backtest_runner=FakeBacktestRunner(),
        )
        report = service.generate_daily_report(symbols=["014943"], options=DailyReportOptions(include_backtest=False))
        engine = ReportTemplateEngine()
        md = engine.render_markdown(report)
        html = engine.render_html(report)
        self.assertIn("分级榜单", md)
        self.assertIn("分级榜单", html)

    def test_sector_flow_failure_is_degraded(self):
        service = DailyReportService(
            source_manager=FailingFlowSourceManager(),
            factor_scorer=FakeFactorScorer(),
            news_service=FakeNewsService(),
            backtest_runner=FakeBacktestRunner(),
        )
        report = service.generate_daily_report(symbols=["014943"], options=DailyReportOptions(include_backtest=False))
        payload = report.to_dict()
        self.assertEqual(payload["sector_ranking"], [])
        self.assertIn("MARKET: SECTOR_FLOW_UNAVAILABLE", payload["risk_alerts"])
        self.assertTrue((payload["evidence"] or {}).get("sector_flow_error"))

    def test_trade_action_blocked_when_news_and_flow_unavailable(self):
        service = DailyReportService(
            source_manager=FakeSourceManager(),
            factor_scorer=GuardrailFactorScorer(),
            news_service=FakeNewsService(),
            backtest_runner=FakeBacktestRunner(),
        )
        report = service.generate_daily_report(symbols=["017193"], options=DailyReportOptions(include_backtest=False))
        payload = report.to_dict()
        detail = payload["fund_details"][0]
        self.assertEqual(detail["tactical_action"], "阻断")
        self.assertIn("TRADE_BLOCKED_DATA_UNAVAILABLE", detail["risk_tags"])
        self.assertIn("017193: TRADE_ACTION_BLOCKED", payload["risk_alerts"])

    def test_backtest_failure_degrades_without_crashing_report(self):
        service = DailyReportService(
            source_manager=FakeSourceManager(),
            factor_scorer=FakeFactorScorer(),
            news_service=FakeNewsService(),
            backtest_runner=FailingBacktestRunner(),
        )
        report = service.generate_daily_report(symbols=["011452"], options=DailyReportOptions(include_backtest=True))
        payload = report.to_dict()
        backtest_summary = payload["fund_details"][0]["backtest_summary"]
        self.assertEqual(backtest_summary["status"], "failed")
        self.assertIn("history snapshot is not enough for backtest", backtest_summary["error_message"])
        self.assertIn("011452: BACKTEST_DATA_UNAVAILABLE", payload["risk_alerts"])


if __name__ == "__main__":
    unittest.main()
