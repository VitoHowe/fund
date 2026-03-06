"""Strategy profile settings, hot reload and replay/tune."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from services.backtest import BacktestConfig, BacktestRunner
from services.config.store import JsonConfigStore, now_utc_iso
from services.strategy.factory import build_strategy

DEFAULT_PROXY_SYMBOL_MAP = {"014943": "159870"}


def _default_strategy_state() -> dict[str, Any]:
    threshold = {
        "id": "score-threshold-default",
        "name": "Score Threshold",
        "strategy_type": "score_threshold",
        "enabled": True,
        "is_default": True,
        "weight": 1.0,
        "params": {
            "buy_threshold": 62.0,
            "sell_threshold": 45.0,
            "min_confidence": 0.55,
        },
    }
    momentum = {
        "id": "score-momentum-default",
        "name": "Score Momentum",
        "strategy_type": "score_momentum",
        "enabled": True,
        "is_default": False,
        "weight": 1.0,
        "params": {
            "entry_score": 55.0,
            "exit_score": 43.0,
            "momentum_window": 3,
            "min_acceleration": 1.5,
        },
    }
    return {
        "default_id": threshold["id"],
        "items": [
            _finalize_profile(threshold, existing=None),
            _finalize_profile(momentum, existing=None),
        ],
    }


class StrategySettingsManager:
    """Manage strategy profiles and instantiate configured strategies."""

    def __init__(self, config_path: str = "config/strategy_profiles.json") -> None:
        self.store = JsonConfigStore(
            config_path=config_path,
            default_factory=_default_strategy_state,
            kind="strategy_profiles",
        )

    def list_profiles(self, *, force_reload: bool = False) -> dict[str, Any]:
        state = self.store.get_state(force_reload=force_reload)
        return self._public_state(state)

    def build_enabled_strategies(self, *, force_reload: bool = False) -> list[Any]:
        state = self.store.get_state(force_reload=force_reload)
        profiles = [item for item in state.get("items") or [] if item.get("enabled")]
        if not profiles:
            profiles = copy.deepcopy(_default_strategy_state()["items"])
        return [build_strategy(item) for item in profiles]

    def create_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        profile = _finalize_profile(payload, existing=None)
        if any(item.get("id") == profile["id"] for item in state["items"]):
            raise ValueError(f"strategy id already exists: {profile['id']}")
        state["items"].append(profile)
        self._sync_default_flags(state, preferred_id=profile["id"] if profile["is_default"] else state.get("default_id"))
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def update_profile(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        existing = self._find_profile(state, strategy_id)
        updated = _finalize_profile(payload, existing=existing)
        for index, current in enumerate(state["items"]):
            if current.get("id") == strategy_id:
                state["items"][index] = updated
                break
        self._sync_default_flags(state, preferred_id=strategy_id if updated["is_default"] else state.get("default_id"))
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def set_default(self, strategy_id: str) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        self._find_profile(state, strategy_id)
        self._sync_default_flags(state, preferred_id=strategy_id)
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def set_enabled(self, strategy_id: str, enabled: bool) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        existing = self._find_profile(state, strategy_id)
        updated = _finalize_profile({"enabled": bool(enabled)}, existing=existing)
        for index, current in enumerate(state["items"]):
            if current.get("id") == strategy_id:
                state["items"][index] = updated
                break
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def rollback_profile(self, strategy_id: str, profile_version: str) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        existing = self._find_profile(state, strategy_id)
        target = next(
            (item for item in existing.get("history") or [] if item.get("profile_version") == profile_version),
            None,
        )
        if target is None:
            raise ValueError(f"strategy version not found: {profile_version}")
        restored = _finalize_profile(target, existing=existing)
        restored["rollback_of"] = profile_version
        for index, current in enumerate(state["items"]):
            if current.get("id") == strategy_id:
                state["items"][index] = restored
                break
        saved = self.store.save_state(state)
        return self._public_state(saved)

    def reload(self) -> dict[str, Any]:
        state = self.store.reload()
        return self._public_state(state)

    def replay_and_tune(
        self,
        strategy_id: str,
        *,
        backtest_runner: BacktestRunner,
        symbols: list[str],
        market_state: str = "neutral",
        limit: int = 120,
        persist: bool = False,
    ) -> dict[str, Any]:
        state = self.store.get_state(force_reload=False)
        profile = self._find_profile(state, strategy_id)
        candidates = _build_candidates(profile)
        results: list[dict[str, Any]] = []
        for index, params in enumerate(candidates):
            candidate_profile = copy.deepcopy(profile)
            candidate_profile["params"] = params
            candidate_profile["profile_version"] = f"candidate-{index + 1}"
            strategy = build_strategy(candidate_profile)
            symbol_results: list[dict[str, Any]] = []
            for symbol in symbols:
                payload = backtest_runner.run(
                    symbol=symbol,
                    strategies=[strategy],
                    market_state=market_state,
                    proxy_symbol=DEFAULT_PROXY_SYMBOL_MAP.get(symbol),
                    limit=limit,
                    config=BacktestConfig(warmup_days=20),
                )
                ranking = (payload.get("ranking") or [{}])[0]
                symbol_results.append(
                    {
                        "symbol": symbol,
                        "total_return_pct": float(ranking.get("total_return_pct") or 0.0),
                        "max_drawdown_pct": float(ranking.get("max_drawdown_pct") or 0.0),
                        "sharpe": float(ranking.get("sharpe") or 0.0),
                    }
                )
            aggregate = _aggregate_tuning_result(symbol_results)
            results.append(
                {
                    "candidate_index": index + 1,
                    "params": params,
                    "aggregate": aggregate,
                    "symbols": symbol_results,
                }
            )
        ranking = sorted(
            results,
            key=lambda item: (
                item["aggregate"]["avg_total_return_pct"],
                item["aggregate"]["avg_sharpe"],
                item["aggregate"]["avg_max_drawdown_pct"],
            ),
            reverse=True,
        )
        best = ranking[0] if ranking else None
        persisted = None
        if persist and best is not None:
            persisted = self.update_profile(strategy_id, {"params": best["params"]})
        return {
            "strategy_id": strategy_id,
            "market_state": market_state,
            "symbols": symbols,
            "config_version": state.get("version"),
            "profile_version": profile.get("profile_version"),
            "ranking": ranking,
            "recommended": best,
            "persisted": persisted,
        }

    def _public_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": state.get("version"),
            "updated_at": state.get("updated_at"),
            "default_id": state.get("default_id"),
            "items": copy.deepcopy(state.get("items") or []),
            "history": copy.deepcopy(state.get("history") or []),
        }

    @staticmethod
    def _find_profile(state: dict[str, Any], strategy_id: str) -> dict[str, Any]:
        for item in state.get("items") or []:
            if item.get("id") == strategy_id:
                return item
        raise ValueError(f"strategy id not found: {strategy_id}")

    def _sync_default_flags(self, state: dict[str, Any], preferred_id: str | None) -> None:
        items = state.get("items") or []
        if not items:
            state["default_id"] = None
            return
        target_id = preferred_id or state.get("default_id") or items[0]["id"]
        state["default_id"] = target_id
        for item in items:
            item["is_default"] = item["id"] == target_id


def _finalize_profile(payload: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    base = copy.deepcopy(existing or {})
    strategy_type = str(payload.get("strategy_type") or base.get("strategy_type") or "").strip().lower()
    if strategy_type not in {"score_threshold", "score_momentum"}:
        raise ValueError(f"unsupported strategy_type: {strategy_type}")
    params = _merge_params(strategy_type, payload.get("params") or {}, base.get("params") or {})
    weight = float(payload.get("weight", base.get("weight", 1.0)))
    profile_id = str(payload.get("id") or base.get("id") or f"{strategy_type}-{weight:g}".replace(".", "-"))
    name = str(payload.get("name") or base.get("name") or strategy_type.replace("_", " ").title()).strip()
    revision = int(base.get("profile_revision") or 0) + 1
    history = list(base.get("history") or [])
    if existing is not None:
        history.insert(0, _snapshot_profile(existing))
    profile = {
        "id": profile_id,
        "name": name,
        "strategy_type": strategy_type,
        "enabled": bool(payload.get("enabled", base.get("enabled", True))),
        "is_default": bool(payload.get("is_default", base.get("is_default", False))),
        "weight": weight,
        "params": params,
        "profile_revision": revision,
        "updated_at": now_utc_iso(),
        "history": history[:12],
    }
    profile["profile_version"] = _build_profile_version(profile)
    return profile


def _build_profile_version(profile: dict[str, Any]) -> str:
    body = {
        "strategy_type": profile.get("strategy_type"),
        "weight": profile.get("weight"),
        "params": profile.get("params") or {},
        "profile_revision": int(profile.get("profile_revision") or 0),
    }
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"p{body['profile_revision']}:{digest}"


def _snapshot_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile.get("id"),
        "name": profile.get("name"),
        "strategy_type": profile.get("strategy_type"),
        "enabled": profile.get("enabled"),
        "is_default": profile.get("is_default"),
        "weight": profile.get("weight"),
        "params": copy.deepcopy(profile.get("params") or {}),
        "profile_revision": profile.get("profile_revision"),
        "profile_version": profile.get("profile_version"),
        "updated_at": profile.get("updated_at"),
    }


def _merge_params(strategy_type: str, payload_params: dict[str, Any], base_params: dict[str, Any]) -> dict[str, Any]:
    if strategy_type == "score_threshold":
        return {
            "buy_threshold": float(payload_params.get("buy_threshold", base_params.get("buy_threshold", 62.0))),
            "sell_threshold": float(payload_params.get("sell_threshold", base_params.get("sell_threshold", 45.0))),
            "min_confidence": float(payload_params.get("min_confidence", base_params.get("min_confidence", 0.55))),
        }
    return {
        "entry_score": float(payload_params.get("entry_score", base_params.get("entry_score", 55.0))),
        "exit_score": float(payload_params.get("exit_score", base_params.get("exit_score", 43.0))),
        "momentum_window": int(payload_params.get("momentum_window", base_params.get("momentum_window", 3))),
        "min_acceleration": float(
            payload_params.get("min_acceleration", base_params.get("min_acceleration", 1.5))
        ),
    }


def _build_candidates(profile: dict[str, Any]) -> list[dict[str, Any]]:
    params = profile.get("params") or {}
    if profile.get("strategy_type") == "score_threshold":
        return [
            {
                "buy_threshold": round(max(50.0, float(params.get("buy_threshold", 62.0)) + delta_buy), 2),
                "sell_threshold": round(max(30.0, float(params.get("sell_threshold", 45.0)) + delta_sell), 2),
                "min_confidence": round(min(0.9, max(0.3, float(params.get("min_confidence", 0.55)) + delta_conf)), 2),
            }
            for delta_buy, delta_sell, delta_conf in [
                (0.0, 0.0, 0.0),
                (-4.0, -2.0, -0.05),
                (3.0, 1.5, 0.0),
                (5.0, -1.0, 0.05),
            ]
        ]
    return [
        {
            "entry_score": round(max(45.0, float(params.get("entry_score", 55.0)) + delta_entry), 2),
            "exit_score": round(max(30.0, float(params.get("exit_score", 43.0)) + delta_exit), 2),
            "momentum_window": max(2, int(params.get("momentum_window", 3)) + delta_window),
            "min_acceleration": round(
                max(0.1, float(params.get("min_acceleration", 1.5)) + delta_acc),
                2,
            ),
        }
        for delta_entry, delta_exit, delta_window, delta_acc in [
            (0.0, 0.0, 0, 0.0),
            (-2.0, -1.0, 1, -0.4),
            (2.5, 1.0, 2, 0.3),
            (4.0, -2.0, -1, 0.6),
        ]
    ]


def _aggregate_tuning_result(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "avg_total_return_pct": 0.0,
            "avg_max_drawdown_pct": 0.0,
            "avg_sharpe": 0.0,
        }
    count = float(len(rows))
    return {
        "avg_total_return_pct": round(sum(item["total_return_pct"] for item in rows) / count, 4),
        "avg_max_drawdown_pct": round(sum(item["max_drawdown_pct"] for item in rows) / count, 4),
        "avg_sharpe": round(sum(item["sharpe"] for item in rows) / count, 4),
    }
