"""Factor scoring orchestration and weight management."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorRegistry, FactorResult


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ScoreCard:
    """Final scoring result for one symbol."""

    symbol: str
    market_state: str
    template_name: str
    weight_version: str
    generated_at: str = field(default_factory=now_utc_iso)
    total_score: float = 0.0
    confidence: float = 0.0
    factor_scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    risk_tags: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WeightTemplateManager:
    """Load and hot-reload factor weight templates from config file."""

    def __init__(self, config_path: str = "config/factor_weights.yaml") -> None:
        self.config_path = config_path
        self._cached_mtime_ns: int | None = None
        self._cached_payload: dict[str, Any] | None = None
        self._cached_version: str | None = None

    def resolve(self, market_state: str, force_reload: bool = False) -> tuple[str, dict[str, float], dict[str, Any], str]:
        payload, version = self._load(force_reload=force_reload)
        templates = payload.get("templates") or {}
        default_template = str(payload.get("default_template") or "neutral")
        template_name = market_state if market_state in templates else default_template
        template_payload = templates.get(template_name) or templates.get(default_template) or {}
        weights = {
            str(name).strip().lower(): float(value)
            for name, value in (template_payload.items() if isinstance(template_payload, dict) else [])
            if float(value) >= 0.0
        }
        thresholds = payload.get("thresholds") or {}
        if not weights:
            raise ValueError("weight template is empty")
        return template_name, weights, thresholds, version

    def _load(self, force_reload: bool) -> tuple[dict[str, Any], str]:
        path = Path(self.config_path)
        if not path.is_absolute():
            root = Path(__file__).resolve().parents[2]
            path = root / path
            self.config_path = str(path)
        stat = path.stat()
        should_reload = force_reload or self._cached_payload is None or self._cached_mtime_ns != stat.st_mtime_ns
        if should_reload:
            text = path.read_text(encoding="utf-8")
            # We intentionally use JSON syntax in *.yaml for zero extra runtime dependencies.
            payload = json.loads(text)
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            version = f"{payload.get('version', 'unknown')}:{digest}"
            self._cached_payload = payload
            self._cached_mtime_ns = stat.st_mtime_ns
            self._cached_version = version
        return self._cached_payload or {}, self._cached_version or "unknown"


class FactorScorer:
    """Compute all factors and aggregate a scorecard."""

    def __init__(
        self,
        source_manager: Any,
        registry: FactorRegistry,
        weight_manager: WeightTemplateManager,
    ) -> None:
        self.source_manager = source_manager
        self.registry = registry
        self.weight_manager = weight_manager

    def score_symbol(
        self,
        symbol: str,
        market_state: str = "neutral",
        proxy_symbol: str | None = None,
        force_reload_weights: bool = False,
        extra_context: dict[str, Any] | None = None,
    ) -> ScoreCard:
        template_name, weights, thresholds, weight_version = self.weight_manager.resolve(
            market_state=market_state,
            force_reload=force_reload_weights,
        )
        context = FactorContext(
            symbol=symbol,
            market_state=market_state,
            proxy_symbol=proxy_symbol,
            extra=dict(extra_context or {}),
        )
        factor_results: dict[str, FactorResult] = {}
        for factor in self.registry.list():
            try:
                result = factor.compute(self.source_manager, context)
            except Exception as exc:  # pragma: no cover
                result = FactorResult(
                    factor=factor.name,
                    score=50.0,
                    confidence=0.1,
                    raw={"error": str(exc)},
                    explanation=f"{factor.name} 执行异常，退化为中性。",
                    risk_tags=["FACTOR_EXECUTION_ERROR"],
                )
            factor_results[result.factor] = result

        total_weight = 0.0
        weighted_score = 0.0
        weighted_confidence = 0.0
        factor_scores: dict[str, dict[str, Any]] = {}
        explanation: list[str] = []
        risk_tags: list[str] = []
        for factor_name, result in factor_results.items():
            weight = float(weights.get(factor_name, 0.0))
            total_weight += weight
            weighted_score += result.score * weight
            weighted_confidence += result.confidence * weight
            contribution = result.score * weight
            factor_scores[factor_name] = {
                **result.to_dict(),
                "weight": weight,
                "contribution": round(contribution, 4),
            }
            explanation.append(
                f"{factor_name}: {result.explanation} 权重 {weight:.2f}，贡献 {contribution:.2f}。"
            )
            for tag in result.risk_tags:
                if tag not in risk_tags:
                    risk_tags.append(tag)
        if total_weight <= 0:
            total_score = 0.0
            confidence = 0.0
        else:
            total_score = weighted_score / total_weight
            confidence = weighted_confidence / total_weight
        min_conf = float(thresholds.get("low_confidence", 0.55))
        if confidence < min_conf and "LOW_CONFIDENCE" not in risk_tags:
            risk_tags.append("LOW_CONFIDENCE")
        return ScoreCard(
            symbol=symbol,
            market_state=market_state,
            template_name=template_name,
            weight_version=weight_version,
            total_score=round(total_score, 4),
            confidence=round(confidence, 4),
            factor_scores=factor_scores,
            risk_tags=risk_tags,
            explanation=explanation,
            trace={
                "weights": weights,
                "thresholds": thresholds,
                "total_weight": round(total_weight, 4),
                "proxy_symbol": proxy_symbol,
            },
        )
