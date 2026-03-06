"""Threshold strategy on total score and confidence."""

from __future__ import annotations

from typing import Any

from services.strategy.base_strategy import IStrategy, StrategySignal


class ScoreThresholdStrategy(IStrategy):
    name = "score_threshold"
    description = "Buy/sell by score thresholds."

    def __init__(
        self,
        buy_threshold: float = 62.0,
        sell_threshold: float = 45.0,
        min_confidence: float = 0.55,
    ) -> None:
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)
        self.min_confidence = float(min_confidence)

    def generate(
        self,
        scorecard: dict[str, Any],
        current_position: float,
        history_scorecards: list[dict[str, Any]],
    ) -> StrategySignal:
        score = float(scorecard.get("total_score", 0.0))
        confidence = float(scorecard.get("confidence", 0.0))
        date = str(scorecard.get("date") or scorecard.get("generated_at") or "")
        action = "hold"
        target = current_position
        reason = "score within hold range"
        if confidence < self.min_confidence:
            action = "sell" if current_position > 0 else "hold"
            target = 0.0
            reason = "confidence below threshold"
        elif score >= self.buy_threshold and current_position <= 0:
            action = "buy"
            target = 1.0
            reason = "score breakout above buy threshold"
        elif score <= self.sell_threshold and current_position > 0:
            action = "sell"
            target = 0.0
            reason = "score breakdown below sell threshold"
        return StrategySignal(
            strategy=self.name,
            action=action,
            target_position=max(0.0, min(1.0, target)),
            reason=reason,
            date=date,
            score=score,
            confidence=confidence,
            metadata={
                "buy_threshold": self.buy_threshold,
                "sell_threshold": self.sell_threshold,
                "min_confidence": self.min_confidence,
            },
        )

