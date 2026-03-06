"""Build strategy instances from config profiles."""

from __future__ import annotations

from typing import Any

from services.strategy.rules import ScoreMomentumStrategy, ScoreThresholdStrategy


def build_strategy(profile: dict[str, Any]) -> Any:
    strategy_type = str(profile.get("strategy_type") or "").strip().lower()
    strategy_name = f"{profile.get('id')}@{profile.get('profile_version')}"
    params = dict(profile.get("params") or {})
    if strategy_type == "score_threshold":
        return ScoreThresholdStrategy(strategy_name=strategy_name, **params)
    if strategy_type == "score_momentum":
        return ScoreMomentumStrategy(strategy_name=strategy_name, **params)
    raise ValueError(f"unsupported strategy_type: {strategy_type}")
