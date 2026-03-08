"""Daily report aggregation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from services.backtest import BacktestConfig, BacktestRunner
from services.factor_engine import FactorScorer
from services.llm import generate_model_summary
from services.news_pipeline import NewsFusionService
from services.reporting.template_engine import (
    DailyReport,
    FundDetail,
    RankingItem,
    ReportTemplateEngine,
    SectorRankingItem,
)
from services.strategy import ScoreMomentumStrategy, ScoreThresholdStrategy
from services.strategy.base_strategy import IStrategy

PROFILE_LABELS = {
    "bear": {"label": "保守", "description": "强调防守与稳定，适合不确定阶段。"},
    "neutral": {"label": "平衡", "description": "兼顾进攻与防守，适合常规盘面。"},
    "bull": {"label": "进取", "description": "强化趋势与动量，适合风险偏好较高场景。"},
}


@dataclass(slots=True)
class DailyReportOptions:
    market_state: str = "neutral"
    news_limit: int = 50
    backtest_limit: int = 120
    include_backtest: bool = True
    stable_only: bool = False


class DailyReportService:
    """Compose ranking, details, tactical suggestions and exports."""

    def __init__(
        self,
        source_manager: Any,
        factor_scorer: FactorScorer,
        news_service: NewsFusionService,
        backtest_runner: BacktestRunner,
        template_engine: ReportTemplateEngine | None = None,
        strategy_provider: Any | None = None,
        strategy_snapshot_provider: Any | None = None,
        model_runtime_provider: Any | None = None,
    ) -> None:
        self.source_manager = source_manager
        self.factor_scorer = factor_scorer
        self.news_service = news_service
        self.backtest_runner = backtest_runner
        self.template_engine = template_engine or ReportTemplateEngine()
        self.strategy_provider = strategy_provider
        self.strategy_snapshot_provider = strategy_snapshot_provider
        self.model_runtime_provider = model_runtime_provider
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
        trace_handle = self.source_manager.begin_trace("daily_report") if hasattr(self.source_manager, "begin_trace") else None
        try:
            active_strategies = self._resolve_strategies()
            strategy_profile = self._resolve_strategy_profile(opts.market_state)

            processed_items, source_stats, raw_news_count = self.news_service.collect_items(limit=opts.news_limit)
            news_source_details = (
                self.news_service.get_last_collection_details()
                if hasattr(self.news_service, "get_last_collection_details")
                else []
            )
            ranking_rows: list[RankingItem] = []
            details: list[FundDetail] = []
            tactical_brief: list[str] = []
            risk_alerts: list[str] = []

            source_options = {"stable_only": opts.stable_only}
            for symbol in symbols:
                related_news = self.news_service.symbol_news(symbol=symbol, items=processed_items)
                feature_extra = self.news_service.build_factor_extra(
                    symbol=symbol,
                    items=related_news,
                    source_options=source_options,
                )
                feature_extra["source_options"] = source_options
                scorecard = self.factor_scorer.score_symbol(
                    symbol=symbol,
                    market_state=opts.market_state,
                    proxy_symbol=proxy_symbol_map.get(symbol),
                    extra_context=feature_extra,
                ).to_dict()
                action, reason = _tactical_from_score(scorecard)
                action, reason = _apply_trade_guardrails(scorecard, action=action, reason=reason)
                name = self._resolve_symbol_name(symbol, stable_only=opts.stable_only)
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
                    try:
                        backtest = self.backtest_runner.run(
                            symbol=symbol,
                            strategies=active_strategies,
                            market_state=opts.market_state,
                            proxy_symbol=proxy_symbol_map.get(symbol),
                            limit=opts.backtest_limit,
                            stable_only=opts.stable_only,
                            config=BacktestConfig(warmup_days=20),
                        )
                        backtest_summary = {
                            "snapshot_hash": backtest.get("snapshot_hash"),
                            "ranking": backtest.get("ranking"),
                            "status": "success",
                            "error_message": None,
                        }
                    except Exception as exc:
                        backtest_summary = {
                            "snapshot_hash": None,
                            "ranking": [],
                            "status": "failed",
                            "error_message": str(exc),
                        }
                detail = FundDetail(
                    symbol=symbol,
                    name=name,
                    tier=_tier_by_score(float(scorecard.get("total_score", 0.0))),
                    confidence=float(scorecard.get("confidence", 0.0)),
                    tactical_action=action,
                    tactical_reason=reason,
                    scorecard=scorecard,
                    news_summary=feature_extra.get("news_feature", {}),
                    news_evidence=_build_news_evidence(related_news),
                    backtest_summary=backtest_summary,
                    factor_breakdown=_build_factor_breakdown(scorecard),
                    chain_status=[],
                    data_source_refs=_collect_source_refs(scorecard),
                    risk_tags=list(scorecard.get("risk_tags") or []),
                    source_time_utc=_extract_source_time(scorecard),
                )
                details.append(detail)
                tactical_brief.append(f"{symbol} -> {action}: {reason}")
                for tag in detail.risk_tags:
                    risk_alerts.append(f"{symbol}: {tag}")
                if backtest_summary.get("status") == "failed":
                    risk_alerts.append(f"{symbol}: BACKTEST_DATA_UNAVAILABLE")
                if action == "阻断":
                    risk_alerts.append(f"{symbol}: TRADE_ACTION_BLOCKED")

            ranking_rows.sort(key=lambda row: row.total_score, reverse=True)
            sector_ranking = self._build_sector_ranking(limit=8, stable_only=opts.stable_only)
            if self._last_sector_flow_error:
                risk_alerts.append("MARKET: SECTOR_FLOW_UNAVAILABLE")

            trace_events = self.source_manager.end_trace(trace_handle) if trace_handle else []
            data_pipeline = _build_pipeline_status(trace_events=trace_events, news_source_details=news_source_details)
            for detail in details:
                detail.chain_status = _build_detail_chain_status(
                    symbol=detail.symbol,
                    scorecard=detail.scorecard,
                    trace_events=trace_events,
                    news_source_details=news_source_details,
                )

            model_usage = self._resolve_model_usage(
                report_date=report_date,
                ranking_rows=ranking_rows,
                strategy_profile=strategy_profile,
                stable_only=opts.stable_only,
            )
            data_pipeline = _append_model_pipeline(data_pipeline, model_usage)
            quality_score = _compute_pipeline_quality(data_pipeline)
            market_summary = _build_market_summary(ranking_rows)
            risk_alerts = sorted(set(risk_alerts))
            recovery_suggestions = _build_recovery_suggestions(data_pipeline=data_pipeline, stable_only=opts.stable_only)
            evidence = {
                "source_stats": source_stats,
                "news_source_details": news_source_details,
                "raw_news_count": raw_news_count,
                "processed_news_count": len(processed_items),
                "generated_by": "DailyReportService",
                "generated_at_utc": now.isoformat(),
                "symbols": symbols,
                "market_state": opts.market_state,
                "sector_flow_error": self._last_sector_flow_error,
                "strategies": [strategy.name for strategy in active_strategies],
                "strategy_profile": strategy_profile,
                "model_usage": model_usage,
                "stable_only": opts.stable_only,
                "trace_event_count": len(trace_events),
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
                strategy_profile=strategy_profile,
                model_usage=model_usage,
                data_pipeline=data_pipeline,
                recovery_suggestions=recovery_suggestions,
                quality_score=quality_score,
            )
        except Exception:
            if trace_handle:
                self.source_manager.end_trace(trace_handle)
            raise

    def _resolve_symbol_name(self, symbol: str, *, stable_only: bool = False) -> str:
        try:
            payload = self.source_manager.fetch_realtime(symbol, bypass_cache=True, stable_only=stable_only)
            records = payload.get("records") or []
            if records and records[0].get("name"):
                return str(records[0]["name"])
        except Exception:
            pass
        return symbol

    def _resolve_strategies(self) -> list[IStrategy]:
        if callable(self.strategy_provider):
            strategies = list(self.strategy_provider() or [])
            if strategies:
                return strategies
        return [ScoreThresholdStrategy(), ScoreMomentumStrategy()]

    def _resolve_strategy_profile(self, market_state: str) -> dict[str, Any]:
        snapshot = (self.strategy_snapshot_provider() or {}) if callable(self.strategy_snapshot_provider) else {}
        profile_meta = PROFILE_LABELS.get(market_state, PROFILE_LABELS["neutral"])
        enabled_profiles = list(snapshot.get("enabled_profiles") or [])
        default_profile = snapshot.get("default_profile") or {}
        return {
            "profile": profile_meta["label"],
            "label": profile_meta["label"],
            "description": profile_meta["description"],
            "market_state": market_state,
            "version": snapshot.get("version"),
            "default_id": snapshot.get("default_id"),
            "default_strategy": {
                "id": default_profile.get("id"),
                "name": default_profile.get("name"),
                "profile_version": default_profile.get("profile_version"),
            },
            "active_strategies": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "profile_version": item.get("profile_version"),
                    "strategy_type": item.get("strategy_type"),
                    "weight": item.get("weight"),
                }
                for item in enabled_profiles
            ],
            "params_snapshot": {
                str(item.get("id")): dict(item.get("params") or {})
                for item in enabled_profiles
                if item.get("id")
            },
        }

    def _resolve_model_usage(
        self,
        *,
        report_date: str,
        ranking_rows: list[RankingItem],
        strategy_profile: dict[str, Any],
        stable_only: bool,
    ) -> dict[str, Any]:
        runtime_model = (self.model_runtime_provider() or {}) if callable(self.model_runtime_provider) else {}
        if not runtime_model or not runtime_model.get("enabled"):
            return {
                "enabled": False,
                "provider": runtime_model.get("provider") if runtime_model else None,
                "model": runtime_model.get("model") if runtime_model else None,
                "latency_ms": None,
                "ok": False,
                "message": "未启用，当前为纯量化引擎",
                "display_name": "纯量化引擎",
                "steps": [
                    {
                        "name": "report_narrative",
                        "status": "not_requested",
                        "latency_ms": None,
                        "summary": "未启用，当前为纯量化引擎",
                    }
                ],
            }

        top_rows = ranking_rows[:3]
        top_symbols = ", ".join(
            f"{row.symbol}({row.tactical_action}/{row.total_score:.1f})"
            for row in top_rows
        )
        prompt = (
            f"今天是 {report_date}。请基于以下量化结果，用中文输出 2 句简短管理摘要。"
            f"策略模板：{strategy_profile.get('label') or strategy_profile.get('profile')}。"
            f"是否仅稳定源：{'是' if stable_only else '否'}。"
            f"核心标的：{top_symbols or '暂无'}。"
        )
        runtime = generate_model_summary(
            url=str(runtime_model.get("url") or ""),
            api_key=str(runtime_model.get("apiKey") or ""),
            model=str(runtime_model.get("model") or ""),
            prompt=prompt,
            timeout=20,
        )
        display_name = f"{runtime_model.get('provider') or runtime_model.get('name')} / {runtime_model.get('model')}"
        return {
            "enabled": True,
            "provider": runtime.get("provider") or runtime_model.get("provider") or runtime_model.get("name"),
            "model": runtime_model.get("model"),
            "latency_ms": runtime.get("latency_ms"),
            "ok": bool(runtime.get("ok")),
            "message": runtime.get("summary") or runtime.get("message") or "model execution completed",
            "display_name": display_name,
            "response_excerpt": runtime.get("response_excerpt"),
            "error_message": None if runtime.get("ok") else runtime.get("message"),
            "steps": [
                {
                    "name": "report_narrative",
                    "status": "success" if runtime.get("ok") else "failed",
                    "latency_ms": runtime.get("latency_ms"),
                    "summary": runtime.get("summary") or runtime.get("message"),
                }
            ],
        }

    def export_report(self, report: DailyReport, fmt: str) -> bytes:
        key = fmt.strip().lower()
        if key == "md":
            return self.template_engine.render_markdown(report).encode("utf-8")
        if key == "html":
            return self.template_engine.render_html(report).encode("utf-8")
        if key == "pdf":
            return self.template_engine.render_pdf_bytes(report)
        raise ValueError(f"unsupported report format: {fmt}")

    def _build_sector_ranking(self, limit: int = 8, *, stable_only: bool = False) -> list[SectorRankingItem]:
        try:
            payload = self.source_manager.fetch_flow(
                symbol=None,
                limit=limit,
                bypass_cache=True,
                stable_only=stable_only,
            )
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


def _apply_trade_guardrails(scorecard: dict[str, Any], *, action: str, reason: str) -> tuple[str, str]:
    risk_tags = set(scorecard.get("risk_tags") or [])
    flow_unavailable = "FLOW_DATA_UNAVAILABLE" in risk_tags
    news_unavailable = bool(risk_tags.intersection({"NEWS_DATA_UNAVAILABLE", "NEWS_EMPTY"}))
    if flow_unavailable and news_unavailable:
        if "TRADE_BLOCKED_DATA_UNAVAILABLE" not in risk_tags:
            scorecard["risk_tags"] = list(risk_tags | {"TRADE_BLOCKED_DATA_UNAVAILABLE"})
        return "阻断", "新闻与资金流链路同时不可用，暂停输出交易建议。"
    return action, reason


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


def _build_news_evidence(items: list[Any], limit: int = 3) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items[:limit]:
        title = str(getattr(item, "title", "") or "")
        if not title or title in seen:
            continue
        seen.add(title)
        evidence.append(
            {
                "title": title,
                "source": getattr(item, "source", None),
                "source_channel": getattr(item, "source_channel", None),
                "published_at_utc": getattr(item, "published_at_utc", None),
                "url": getattr(item, "url", None),
                "sentiment_label": getattr(item, "sentiment_label", None),
            }
        )
    return evidence


def _build_factor_breakdown(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    factors = scorecard.get("factor_scores") or {}
    for factor_name, payload in sorted(factors.items()):
        rows.append(
            {
                "factor": factor_name,
                "score": round(float(payload.get("score") or 0.0), 2),
                "confidence": round(float(payload.get("confidence") or 0.0), 2),
                "weight": round(float(payload.get("weight") or 0.0), 4),
                "contribution": round(float(payload.get("contribution") or 0.0), 4),
                "explanation": payload.get("explanation"),
                "risk_tags": list(payload.get("risk_tags") or []),
                "source_refs": list(payload.get("source_refs") or []),
                "stale": bool(payload.get("stale")),
            }
        )
    return rows


def _build_pipeline_status(
    *,
    trace_events: list[dict[str, Any]],
    news_source_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}
    for event in trace_events:
        if event.get("type") == "trace_start":
            continue
        key = str(event.get("source") or "unknown")
        entry = aggregated.setdefault(
            key,
            {
                "source": key,
                "status": "not_requested",
                "latency_total": 0.0,
                "latency_count": 0,
                "fallback_source": None,
                "quality_total": 0.0,
                "quality_count": 0,
                "error_message": None,
                "error_type": None,
                "metrics": set(),
            },
        )
        entry["status"] = _merge_status(entry.get("status"), str(event.get("status") or "not_requested"))
        latency_ms = event.get("latency_ms")
        if latency_ms is not None:
            entry["latency_total"] += float(latency_ms)
            entry["latency_count"] += 1
        quality_score = event.get("quality_score")
        if quality_score is not None:
            entry["quality_total"] += float(quality_score)
            entry["quality_count"] += 1
        if event.get("fallback_source") and not entry.get("fallback_source"):
            entry["fallback_source"] = event.get("fallback_source")
        if event.get("error_message"):
            entry["error_message"] = event.get("error_message")
        if event.get("error_type"):
            entry["error_type"] = event.get("error_type")
        if event.get("metric"):
            entry["metrics"].add(str(event.get("metric")))

    for detail in news_source_details:
        key = str(detail.get("source") or "unknown")
        entry = aggregated.setdefault(
            key,
            {
                "source": key,
                "status": "not_requested",
                "latency_total": 0.0,
                "latency_count": 0,
                "fallback_source": None,
                "quality_total": 0.0,
                "quality_count": 0,
                "error_message": None,
                "error_type": None,
                "metrics": set(),
            },
        )
        entry["status"] = _merge_status(entry.get("status"), str(detail.get("status") or "not_requested"))
        if detail.get("latency_ms") is not None:
            entry["latency_total"] += float(detail.get("latency_ms") or 0.0)
            entry["latency_count"] += 1
        if detail.get("quality_score") is not None:
            entry["quality_total"] += float(detail.get("quality_score"))
            entry["quality_count"] += 1
        if detail.get("error_message"):
            entry["error_message"] = detail.get("error_message")
        entry["metrics"].add("news_pipeline")

    rows = []
    for entry in aggregated.values():
        rows.append(
            {
                "source": entry["source"],
                "status": entry["status"],
                "latency_ms": round(entry["latency_total"] / entry["latency_count"], 2)
                if entry["latency_count"]
                else None,
                "fallback_source": entry["fallback_source"],
                "quality_score": round(entry["quality_total"] / entry["quality_count"], 4)
                if entry["quality_count"]
                else None,
                "error_message": entry["error_message"],
                "error_type": entry["error_type"],
                "metrics": sorted(entry["metrics"]),
            }
        )
    rows.sort(key=lambda item: (_status_order(item.get("status")), item.get("source") or ""))
    return rows


def _build_detail_chain_status(
    *,
    symbol: str,
    scorecard: dict[str, Any],
    trace_events: list[dict[str, Any]],
    news_source_details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    factor_scores = scorecard.get("factor_scores") or {}
    for factor_name, payload in sorted(factor_scores.items()):
        rows.append(
            {
                "source": f"factor:{factor_name}",
                "status": _factor_status(payload),
                "latency_ms": None,
                "fallback_source": None,
                "quality_score": round(float(payload.get("confidence") or 0.0), 4),
                "error_message": (payload.get("raw") or {}).get("error"),
                "error_type": "factor" if (payload.get("raw") or {}).get("error") else None,
                "refs": list(payload.get("source_refs") or []),
            }
        )

    symbol_events = [
        event
        for event in trace_events
        if event.get("type") != "trace_start"
        and (event.get("symbol") in {symbol, None})
    ]
    source_rows = _build_pipeline_status(trace_events=symbol_events, news_source_details=news_source_details)
    rows.extend(source_rows)
    return rows


def _append_model_pipeline(data_pipeline: list[dict[str, Any]], model_usage: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(data_pipeline)
    rows.append(
        {
            "source": "model.runtime",
            "status": (model_usage.get("steps") or [{}])[0].get("status", "not_requested"),
            "latency_ms": model_usage.get("latency_ms"),
            "fallback_source": None,
            "quality_score": 1.0 if model_usage.get("enabled") and model_usage.get("ok") else None,
            "error_message": model_usage.get("error_message"),
            "error_type": "model" if model_usage.get("error_message") else None,
            "metrics": ["report_narrative"],
        }
    )
    rows.sort(key=lambda item: (_status_order(item.get("status")), item.get("source") or ""))
    return rows


def _compute_pipeline_quality(rows: list[dict[str, Any]]) -> float | None:
    scores = [float(item.get("quality_score")) for item in rows if item.get("quality_score") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _build_recovery_suggestions(*, data_pipeline: list[dict[str, Any]], stable_only: bool) -> list[dict[str, Any]]:
    suggestions = [
        {
            "action": "retry",
            "label": "重试当前报告",
            "description": "重新触发一次报告生成，优先验证是否为瞬时波动。",
        }
    ]
    failed = [item for item in data_pipeline if item.get("status") == "failed"]
    degraded = [item for item in data_pipeline if item.get("status") in {"partial_success", "fallback_cache"}]
    if failed:
        suggestions.append(
            {
                "action": "switch_profile",
                "label": "切换策略模板",
                "description": "当前链路异常时可先切到保守或平衡模板，降低波动依赖。",
            }
        )
    if (failed or degraded) and not stable_only:
        suggestions.append(
            {
                "action": "stable_only",
                "label": "仅使用稳定源",
                "description": "跳过当前不稳定来源，使用健康源重新生成报告。",
            }
        )
    return suggestions


def _merge_status(current: str | None, incoming: str) -> str:
    if not current or current == "not_requested":
        return incoming
    if current == incoming:
        return current
    states = {current, incoming}
    if "partial_success" in states:
        return "partial_success"
    if "failed" in states and ("success" in states or "fallback_cache" in states):
        return "partial_success"
    if "success" in states and "fallback_cache" in states:
        return "partial_success"
    if incoming != "not_requested":
        return incoming
    return current


def _status_order(status: str | None) -> int:
    order = {
        "failed": 0,
        "partial_success": 1,
        "fallback_cache": 2,
        "success": 3,
        "not_requested": 4,
    }
    return order.get(str(status or "not_requested"), 9)


def _factor_status(payload: dict[str, Any]) -> str:
    raw = payload.get("raw") or {}
    if raw.get("error"):
        return "failed"
    if payload.get("stale"):
        return "partial_success"
    return "success"
