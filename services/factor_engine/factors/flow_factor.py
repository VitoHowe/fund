"""Flow factor."""

from __future__ import annotations

from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorResult, IFactor
from services.factor_engine.factors.common import linear_score


class FlowFactor(IFactor):
    name = "flow"
    description = "Flow score from net inflow and turnover related proxies."

    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        target_symbol = context.proxy_symbol or context.symbol
        fallback_used = target_symbol != context.symbol
        try:
            payload = source_manager.fetch_flow(target_symbol, limit=20)
            records = payload.get("records") or []
            if not records:
                raise ValueError("empty flow records")
            row = records[0]
            flow_ratio = _to_float(row.get("main_inflow_ratio"))
            if flow_ratio is None:
                flow_ratio = _to_float(row.get("change_pct"))
            if flow_ratio is None:
                flow_ratio = 0.0
            score = linear_score(flow_ratio, low=-5.0, high=5.0)
            confidence = 0.8 if not payload.get("stale") else 0.5
            risks: list[str] = []
            if flow_ratio < 0:
                risks.append("FLOW_OUTFLOW")
            if fallback_used:
                risks.append("FLOW_PROXY_SYMBOL")
            return FactorResult(
                factor=self.name,
                score=score,
                confidence=confidence,
                raw={
                    "target_symbol": target_symbol,
                    "main_inflow_ratio": flow_ratio,
                    "fallback_proxy_symbol": fallback_used,
                },
                explanation=(
                    f"资金因子使用 {target_symbol}，主力净流入比 {flow_ratio:.2f}% ，"
                    f"映射得分 {score:.1f}。"
                ),
                risk_tags=risks,
                source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
                stale=bool(payload.get("stale")),
            )
        except Exception as exc:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.2,
                raw={"target_symbol": target_symbol, "error": str(exc), "fallback_proxy_symbol": fallback_used},
                explanation="资金流数据不可用，因子退化为中性。",
                risk_tags=["FLOW_DATA_UNAVAILABLE"],
                source_refs=[],
                stale=True,
            )


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

