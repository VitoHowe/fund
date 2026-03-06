"""Factor base contracts and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class FactorContext:
    """Execution context for one symbol scoring."""

    symbol: str
    market_state: str = "neutral"
    proxy_symbol: str | None = None
    as_of_utc: str = field(default_factory=now_utc_iso)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FactorResult:
    """One factor output with explanation and risk tags."""

    factor: str
    score: float
    confidence: float
    raw: dict[str, Any]
    explanation: str
    risk_tags: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    stale: bool = False

    def __post_init__(self) -> None:
        self.score = clamp_score(self.score)
        self.confidence = clamp_confidence(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IFactor(ABC):
    """Factor interface."""

    name: str
    description: str

    @abstractmethod
    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        raise NotImplementedError


class FactorRegistry:
    """In-memory factor registry."""

    def __init__(self) -> None:
        self._factors: dict[str, IFactor] = {}

    def register(self, factor: IFactor) -> None:
        key = factor.name.strip().lower()
        if not key:
            raise ValueError("factor name is required")
        if key in self._factors:
            raise ValueError(f"factor already registered: {factor.name}")
        self._factors[key] = factor

    def get(self, name: str) -> IFactor:
        key = name.strip().lower()
        if key not in self._factors:
            raise KeyError(f"factor not found: {name}")
        return self._factors[key]

    def list(self) -> list[IFactor]:
        return [self._factors[name] for name in sorted(self._factors.keys())]

