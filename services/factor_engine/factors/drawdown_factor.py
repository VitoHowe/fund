"""Drawdown factor."""

from __future__ import annotations

from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorResult, IFactor
from services.factor_engine.factors.common import extract_nav_series, linear_score, max_drawdown_pct


class DrawdownFactor(IFactor):
    name = "drawdown"
    description = "Drawdown risk from historical NAV path."

    def __init__(self, lookback: int = 60) -> None:
        self.lookback = max(10, int(lookback))

    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        payload = source_manager.fetch_history(context.symbol, limit=max(self.lookback, 90))
        series = extract_nav_series(payload)
        if len(series) < 2:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.2,
                raw={"lookback": self.lookback, "reason": "insufficient_history"},
                explanation="历史净值不足，回撤因子退化为中性。",
                risk_tags=["INSUFFICIENT_HISTORY"],
                source_refs=[payload.get("source", "unknown")],
                stale=bool(payload.get("stale")),
            )
        nav_values = [item[1] for item in (series[-self.lookback :] if len(series) > self.lookback else series)]
        drawdown_pct = max_drawdown_pct(nav_values)
        score = linear_score(drawdown_pct, low=-30.0, high=0.0)
        confidence = min(1.0, 0.3 + len(nav_values) / self.lookback * 0.7)
        risks: list[str] = []
        if drawdown_pct <= -15.0:
            risks.append("DRAWDOWN_DEEP")
        return FactorResult(
            factor=self.name,
            score=score,
            confidence=confidence,
            raw={"lookback": self.lookback, "max_drawdown_pct": round(drawdown_pct, 4)},
            explanation=f"{self.lookback} 日最大回撤 {drawdown_pct:.2f}% ，映射稳健得分 {score:.1f}。",
            risk_tags=risks,
            source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
            stale=bool(payload.get("stale")),
        )

