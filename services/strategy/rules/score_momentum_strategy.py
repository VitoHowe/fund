"""Momentum strategy on score acceleration."""

from __future__ import annotations

from typing import Any

from services.strategy.base_strategy import IStrategy, StrategySignal


class ScoreMomentumStrategy(IStrategy):
    name = "score_momentum"
    description = "Use score momentum and trend filter for decisions."

    def __init__(
        self,
        entry_score: float = 55.0,
        exit_score: float = 43.0,
        momentum_window: int = 3,
        min_acceleration: float = 1.5,
        strategy_name: str | None = None,
    ) -> None:
        self.entry_score = float(entry_score)
        self.exit_score = float(exit_score)
        self.momentum_window = max(2, int(momentum_window))
        self.min_acceleration = float(min_acceleration)
        self.name = strategy_name or self.name

    def generate(
        self,
        scorecard: dict[str, Any],
        current_position: float,
        history_scorecards: list[dict[str, Any]],
    ) -> StrategySignal:
        date = str(scorecard.get("date") or scorecard.get("generated_at") or "")
        score = float(scorecard.get("total_score", 0.0))
        confidence = float(scorecard.get("confidence", 0.0))
        recent = history_scorecards[-self.momentum_window :]
        if recent:
            avg_recent = sum(float(item.get("total_score", 0.0)) for item in recent) / len(recent)
        else:
            avg_recent = score
        acceleration = score - avg_recent
        action = "hold"
        target = current_position
        reason = "no regime switch"
        if score <= self.exit_score and current_position > 0:
            action = "sell"
            target = 0.0
            reason = "score dropped below exit threshold"
        elif (
            current_position <= 0
            and score >= self.entry_score
            and acceleration >= self.min_acceleration
            and confidence >= 0.5
        ):
            action = "buy"
            target = 1.0
            reason = "score momentum acceleration confirmed"
        elif current_position > 0 and acceleration < -self.min_acceleration:
            action = "sell"
            target = 0.0
            reason = "score momentum reversal"
        return StrategySignal(
            strategy=self.name,
            action=action,
            target_position=max(0.0, min(1.0, target)),
            reason=reason,
            date=date,
            score=score,
            confidence=confidence,
            metadata={
                "entry_score": self.entry_score,
                "exit_score": self.exit_score,
                "momentum_window": self.momentum_window,
                "acceleration": round(acceleration, 4),
            },
        )

