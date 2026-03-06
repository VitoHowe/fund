"""Volatility factor."""

from __future__ import annotations

from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorResult, IFactor
from services.factor_engine.factors.common import extract_nav_series, extract_return_series, std_pct


class VolatilityFactor(IFactor):
    name = "volatility"
    description = "Volatility score from daily return dispersion."

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = max(5, int(lookback))

    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        payload = source_manager.fetch_history(context.symbol, limit=max(self.lookback + 10, 45))
        nav_series = extract_nav_series(payload)
        returns = extract_return_series(payload, nav_series)
        window = returns[-self.lookback :] if len(returns) >= self.lookback else returns
        if not window:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.2,
                raw={"lookback": self.lookback, "reason": "no_return_series"},
                explanation="缺少可用收益率序列，波动因子退化为中性。",
                risk_tags=["INSUFFICIENT_HISTORY"],
                source_refs=[payload.get("source", "unknown")],
                stale=bool(payload.get("stale")),
            )
        vol_pct = std_pct(window)
        score = max(0.0, min(100.0, 100.0 - vol_pct / 5.0 * 100.0))
        confidence = min(1.0, 0.3 + len(window) / self.lookback * 0.7)
        risks: list[str] = []
        if vol_pct >= 3.0:
            risks.append("VOLATILITY_HIGH")
        return FactorResult(
            factor=self.name,
            score=score,
            confidence=confidence,
            raw={"lookback": self.lookback, "volatility_pct": round(vol_pct, 4)},
            explanation=f"{self.lookback} 日波动率 {vol_pct:.2f}% ，映射防守得分 {score:.1f}。",
            risk_tags=risks,
            source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
            stale=bool(payload.get("stale")),
        )

