"""Daily report aggregation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.backtest import BacktestConfig, BacktestRunner
from services.factor_engine import FactorScorer
from services.news_pipeline import NewsFusionService
from services.reporting.template_engine import (
    DailyReport,
    FundDetail,
    RankingItem,
    ReportTemplateEngine,
    SectorRankingItem,
)
from services.strategy import ScoreMomentumStrategy, ScoreThresholdStrategy


@dataclass(slots=True)
class DailyReportOptions:
    market_state: str = "neutral"
    news_limit: int = 50
    backtest_limit: int = 120
    include_backtest: bool = True


class DailyReportService:
    """Compose ranking, details, tactical suggestions and exports."""

    def __init__(
        self,
        source_manager: Any,
        factor_scorer: FactorScorer,
        news_service: NewsFusionService,
        backtest_runner: BacktestRunner,
        template_engine: ReportTemplateEngine | None = None,
    ) -> None:
        self.source_manager = source_manager
        self.factor_scorer = factor_scorer
        self.news_service = news_service
        self.backtest_runner = backtest_runner
        self.template_engine = template_engine or ReportTemplateEngine()
        self._last_sector_flow_error: str | None = None

    def generate_daily_report(
        self,
        symbols: list[str],
        proxy_symbol_map: dict[str, str] | None = None,
        options: DailyReportOptions | None = None,
    ) -> DailyReport:
        opts = options or DailyReportOptions()
        proxy_symbol_map = proxy_symbol_map or {}
        self._last_sector_flow_error = None
        now = datetime.now(timezone.utc)
        report_date = now.astimezone().strftime("%Y-%m-%d")
        report_id = f"rpt-{report_date.replace('-', '')}-{now.strftime('%H%M%S')}"

        processed_items, source_stats, raw_news_count = self.news_service.collect_items(limit=opts.news_limit)
        ranking_rows: list[RankingItem] = []
        details: list[FundDetail] = []
        tactical_brief: list[str] = []
        risk_alerts: list[str] = []

        for symbol in symbols:
            related_news = self.news_service.symbol_news(symbol=symbol, items=processed_items)
            feature_extra = self.news_service.build_factor_extra(symbol=symbol, items=related_news)
            scorecard = self.factor_scorer.score_symbol(
                symbol=symbol,
                market_state=opts.market_state,
                proxy_symbol=proxy_symbol_map.get(symbol),
                extra_context=feature_extra,
            ).to_dict()
            action, reason = _tactical_from_score(scorecard)
            name = self._resolve_symbol_name(symbol)
            ranking_rows.append(
                RankingItem(
                    symbol=symbol,
                    name=name,
                    tier=_tier_by_score(float(scorecard.get("total_score", 0.0))),
                    total_score=float(scorecard.get("total_score", 0.0)),
                    confidence=float(scorecard.get("confidence", 0.0)),
                    tactical_action=action,
                    tactical_reason=reason,
                    risk_tags=list(scorecard.get("risk_tags") or []),
                )
            )
            backtest_summary: dict[str, Any] = {}
            if opts.include_backtest:
                backtest = self.backtest_runner.run(
                    symbol=symbol,
                    strategies=[ScoreThresholdStrategy(), ScoreMomentumStrategy()],
                    market_state=opts.market_state,
                    proxy_symbol=proxy_symbol_map.get(symbol),
                    limit=opts.backtest_limit,
                    config=BacktestConfig(warmup_days=20),
                )
                backtest_summary = {
                    "snapshot_hash": backtest.get("snapshot_hash"),
                    "ranking": backtest.get("ranking"),
                }
            detail = FundDetail(
                symbol=symbol,
                name=name,
                scorecard=scorecard,
                news_summary=feature_extra.get("news_feature", {}),
                backtest_summary=backtest_summary,
                data_source_refs=_collect_source_refs(scorecard),
                source_time_utc=_extract_source_time(scorecard),
            )
            details.append(detail)
            tactical_brief.append(f"{symbol} -> {action}: {reason}")
            for tag in detail.scorecard.get("risk_tags") or []:
                risk_alerts.append(f"{symbol}: {tag}")

        ranking_rows.sort(key=lambda row: row.total_score, reverse=True)
        sector_ranking = self._build_sector_ranking(limit=8)
        if self._last_sector_flow_error:
            risk_alerts.append("MARKET: SECTOR_FLOW_UNAVAILABLE")
        market_summary = _build_market_summary(ranking_rows)
        risk_alerts = sorted(set(risk_alerts))
        evidence = {
            "source_stats": source_stats,
            "raw_news_count": raw_news_count,
            "processed_news_count": len(processed_items),
            "generated_by": "DailyReportService",
            "generated_at_utc": now.isoformat(),
            "symbols": symbols,
            "market_state": opts.market_state,
            "sector_flow_error": self._last_sector_flow_error,
        }
        return DailyReport(
            report_id=report_id,
            report_date=report_date,
            generated_at_utc=now.isoformat(),
            market_summary=market_summary,
            tactical_brief=tactical_brief,
            ranking=ranking_rows,
            sector_ranking=sector_ranking,
            fund_details=details,
            risk_alerts=risk_alerts,
            evidence=evidence,
        )

    def _resolve_symbol_name(self, symbol: str) -> str:
        try:
            payload = self.source_manager.fetch_realtime(symbol, bypass_cache=True)
            records = payload.get("records") or []
            if records and records[0].get("name"):
                return str(records[0]["name"])
        except Exception:
            pass
        return symbol

    def export_report(self, report: DailyReport, fmt: str) -> bytes:
        key = fmt.strip().lower()
        if key == "md":
            return self.template_engine.render_markdown(report).encode("utf-8")
        if key == "html":
            return self.template_engine.render_html(report).encode("utf-8")
        if key == "pdf":
            return self.template_engine.render_pdf_bytes(report)
        raise ValueError(f"unsupported report format: {fmt}")

    def _build_sector_ranking(self, limit: int = 8) -> list[SectorRankingItem]:
        try:
            payload = self.source_manager.fetch_flow(symbol=None, limit=limit, bypass_cache=True)
            rows = payload.get("records") or []
            self._last_sector_flow_error = None
        except Exception as exc:
            self._last_sector_flow_error = str(exc)
            return []
        out: list[SectorRankingItem] = []
        for row in rows[:limit]:
            out.append(
                SectorRankingItem(
                    sector=str(row.get("sector") or "未知板块"),
                    change_pct=float(row.get("change_pct") or 0.0),
                    main_net_inflow=float(row.get("main_net_inflow") or 0.0),
                    main_inflow_ratio=float(row.get("main_inflow_ratio") or 0.0),
                    top_stock=row.get("top_stock"),
                )
            )
        return out


def _tactical_from_score(scorecard: dict[str, Any]) -> tuple[str, str]:
    score = float(scorecard.get("total_score", 0.0))
    confidence = float(scorecard.get("confidence", 0.0))
    if confidence < 0.55:
        return "观望", "置信度不足，等待更多证据"
    if score >= 70:
        return "增持", "总分高且风险可控"
    if score >= 55:
        return "持有", "结构中性偏多，继续跟踪"
    return "减仓", "总分偏弱或风险标签偏多"


def _build_market_summary(rows: list[RankingItem]) -> dict[str, Any]:
    if not rows:
        return {"symbol_count": 0, "avg_score": 0.0, "bullish_ratio": 0.0, "low_confidence_ratio": 0.0}
    avg_score = sum(item.total_score for item in rows) / len(rows)
    bullish = sum(1 for item in rows if item.tactical_action in ("增持", "持有"))
    low_conf = sum(1 for item in rows if item.confidence < 0.55)
    return {
        "symbol_count": len(rows),
        "avg_score": round(avg_score, 4),
        "bullish_ratio": round(bullish / len(rows), 4),
        "low_confidence_ratio": round(low_conf / len(rows), 4),
    }


def _collect_source_refs(scorecard: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    factors = scorecard.get("factor_scores") or {}
    for item in factors.values():
        for ref in item.get("source_refs") or []:
            if ref not in refs:
                refs.append(ref)
    return refs


def _extract_source_time(scorecard: dict[str, Any]) -> str | None:
    factors = scorecard.get("factor_scores") or {}
    sentiment = factors.get("sentiment") or {}
    raw = sentiment.get("raw") or {}
    if raw.get("latest_news_time_utc"):
        return str(raw.get("latest_news_time_utc"))
    return None


def _tier_by_score(score: float) -> str:
    if score >= 75:
        return "S"
    if score >= 65:
        return "A"
    if score >= 55:
        return "B"
    if score >= 45:
        return "C"
    return "D"
