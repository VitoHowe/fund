"""Trend factor."""

from __future__ import annotations

from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorResult, IFactor
from services.factor_engine.factors.common import extract_nav_series, linear_score, pct_change


class TrendFactor(IFactor):
    name = "trend"
    description = "Trend based on historical NAV slope."

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = max(5, int(lookback))

    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        payload = source_manager.fetch_history(context.symbol, limit=max(self.lookback, 40))
        series = extract_nav_series(payload)
        if len(series) < 2:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.2,
                raw={"lookback": self.lookback, "reason": "insufficient_history"},
                explanation="历史净值样本不足，趋势因子退化为中性。",
                risk_tags=["INSUFFICIENT_HISTORY"],
                source_refs=[payload.get("source", "unknown")],
                stale=bool(payload.get("stale")),
            )
        window = series[-self.lookback :] if len(series) >= self.lookback else series
        start_nav = window[0][1]
        end_nav = window[-1][1]
        trend_return = pct_change(start_nav, end_nav)
        score = linear_score(trend_return, low=-8.0, high=8.0)
        confidence = min(1.0, 0.3 + len(window) / self.lookback * 0.7)
        risks: list[str] = []
        if trend_return < 0:
            risks.append("TREND_WEAK")
        return FactorResult(
            factor=self.name,
            score=score,
            confidence=confidence,
            raw={"lookback": self.lookback, "trend_return_pct": round(trend_return, 4)},
            explanation=f"{self.lookback} 日趋势收益 {trend_return:.2f}%，映射趋势得分 {score:.1f}。",
            risk_tags=risks,
            source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
            stale=bool(payload.get("stale")),
        )

