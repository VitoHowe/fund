"""Factor engine entrypoints."""

from services.factor_engine.base_factor import FactorRegistry
from services.factor_engine.factors import (
    DrawdownFactor,
    FlowFactor,
    MomentumFactor,
    SentimentFactor,
    TrendFactor,
    VolatilityFactor,
)
from services.factor_engine.scoring import FactorScorer, ScoreCard, WeightTemplateManager


def build_default_factor_registry() -> FactorRegistry:
    registry = FactorRegistry()
    registry.register(TrendFactor(lookback=20))
    registry.register(MomentumFactor(short_window=5, long_window=20))
    registry.register(VolatilityFactor(lookback=20))
    registry.register(DrawdownFactor(lookback=60))
    registry.register(FlowFactor())
    registry.register(SentimentFactor(limit=20))
    return registry


__all__ = [
    "FactorScorer",
    "ScoreCard",
    "WeightTemplateManager",
    "build_default_factor_registry",
]

