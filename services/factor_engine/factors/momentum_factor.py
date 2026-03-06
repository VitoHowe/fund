"""Momentum factor."""

from __future__ import annotations

from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorResult, IFactor
from services.factor_engine.factors.common import extract_nav_series, linear_score, pct_change


class MomentumFactor(IFactor):
    name = "momentum"
    description = "Cross-window momentum spread."

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        self.short_window = max(3, int(short_window))
        self.long_window = max(self.short_window + 2, int(long_window))

    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        payload = source_manager.fetch_history(context.symbol, limit=max(self.long_window + 5, 45))
        series = extract_nav_series(payload)
        if len(series) < self.long_window:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.25,
                raw={"short_window": self.short_window, "long_window": self.long_window},
                explanation="历史窗口不足，动量因子退化为中性。",
                risk_tags=["INSUFFICIENT_HISTORY"],
                source_refs=[payload.get("source", "unknown")],
                stale=bool(payload.get("stale")),
            )
        short_start = series[-self.short_window][1]
        long_start = series[-self.long_window][1]
        end_nav = series[-1][1]
        short_ret = pct_change(short_start, end_nav)
        long_ret = pct_change(long_start, end_nav)
        spread = short_ret - long_ret
        score = linear_score(spread, low=-6.0, high=6.0)
        confidence = min(1.0, 0.4 + len(series) / (self.long_window * 1.2))
        risks: list[str] = []
        if spread < 0:
            risks.append("MOMENTUM_DECAY")
        return FactorResult(
            factor=self.name,
            score=score,
            confidence=confidence,
            raw={
                "short_window": self.short_window,
                "long_window": self.long_window,
                "short_return_pct": round(short_ret, 4),
                "long_return_pct": round(long_ret, 4),
                "spread_pct": round(spread, 4),
            },
            explanation=(
                f"短期动量 {short_ret:.2f}%、长期动量 {long_ret:.2f}%、动量差 {spread:.2f}% ，"
                f"映射得分 {score:.1f}。"
            ),
            risk_tags=risks,
            source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
            stale=bool(payload.get("stale")),
        )

