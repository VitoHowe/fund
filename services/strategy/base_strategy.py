"""Strategy contracts for score-driven signal generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class StrategySignal:
    """One strategy decision at a timestamp."""

    strategy: str
    action: str
    target_position: float
    reason: str
    date: str
    score: float
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IStrategy(ABC):
    """Strategy interface."""

    name: str
    description: str

    @abstractmethod
    def generate(
        self,
        scorecard: dict[str, Any],
        current_position: float,
        history_scorecards: list[dict[str, Any]],
    ) -> StrategySignal:
        raise NotImplementedError

