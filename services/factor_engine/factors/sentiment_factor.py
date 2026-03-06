"""Sentiment factor."""

from __future__ import annotations

from typing import Any

from services.factor_engine.base_factor import FactorContext, FactorResult, IFactor
from services.factor_engine.factors.common import linear_score


POSITIVE_WORDS = ("利好", "增长", "上调", "突破", "回暖", "提振", "增持", "净流入")
NEGATIVE_WORDS = ("利空", "下滑", "下调", "风险", "回撤", "减持", "净流出", "波动")


class SentimentFactor(IFactor):
    name = "sentiment"
    description = "News sentiment from keyword polarity."

    def __init__(self, limit: int = 20) -> None:
        self.limit = max(5, int(limit))

    def compute(self, source_manager: Any, context: FactorContext) -> FactorResult:
        feature = (context.extra or {}).get("news_feature")
        if isinstance(feature, dict) and int(feature.get("rows", 0)) > 0:
            rows = int(feature.get("rows", 0))
            weighted_sent = float(feature.get("credibility_weighted_sentiment", feature.get("avg_sentiment", 0.0)))
            score = linear_score(weighted_sent, low=-1.0, high=1.0)
            confidence = min(1.0, 0.35 + rows * 0.03)
            tags: list[str] = list(feature.get("tags") or [])
            neg_ratio = float(feature.get("negative_ratio", 0.0))
            if neg_ratio >= 0.45 and "SENTIMENT_NEGATIVE" not in tags:
                tags.append("SENTIMENT_NEGATIVE")
            return FactorResult(
                factor=self.name,
                score=score,
                confidence=confidence,
                raw={
                    "rows": rows,
                    "avg_sentiment": float(feature.get("avg_sentiment", 0.0)),
                    "credibility_weighted_sentiment": weighted_sent,
                    "positive_ratio": float(feature.get("positive_ratio", 0.0)),
                    "negative_ratio": neg_ratio,
                    "latest_news_time_utc": feature.get("latest_news_time_utc"),
                },
                explanation=(
                    f"使用新闻融合特征：样本 {rows} 条，加权情绪 {weighted_sent:.3f}，"
                    f"情绪得分 {score:.1f}。"
                ),
                risk_tags=tags,
                source_refs=["news_pipeline:feature_summary"],
                stale=False,
            )
        try:
            payload = source_manager.fetch_news(symbol=context.symbol, limit=self.limit)
        except Exception as exc:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.2,
                raw={"error": str(exc), "rows": 0},
                explanation="新闻链路不可用，情绪因子退化为中性。",
                risk_tags=["NEWS_DATA_UNAVAILABLE"],
                source_refs=[],
                stale=True,
            )
        records = payload.get("records") or []
        if not records:
            return FactorResult(
                factor=self.name,
                score=50.0,
                confidence=0.2,
                raw={"rows": 0},
                explanation="未获取到新闻样本，情绪因子退化为中性。",
                risk_tags=["NEWS_EMPTY"],
                source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
                stale=bool(payload.get("stale")),
            )
        pos_hits = 0
        neg_hits = 0
        for row in records:
            text = f"{row.get('title', '')} {row.get('content', '')}"
            pos_hits += sum(1 for token in POSITIVE_WORDS if token in text)
            neg_hits += sum(1 for token in NEGATIVE_WORDS if token in text)
        total_hits = pos_hits + neg_hits
        polarity = (pos_hits - neg_hits) / max(total_hits, 1)
        score = linear_score(polarity, low=-1.0, high=1.0)
        confidence = min(1.0, 0.35 + len(records) * 0.03)
        risks: list[str] = []
        if polarity < -0.2:
            risks.append("SENTIMENT_NEGATIVE")
        if (payload.get("metadata") or {}).get("fallback_mode"):
            risks.append("NEWS_SYMBOL_FALLBACK")
        return FactorResult(
            factor=self.name,
            score=score,
            confidence=confidence,
            raw={"rows": len(records), "positive_hits": pos_hits, "negative_hits": neg_hits, "polarity": polarity},
            explanation=(
                f"新闻样本 {len(records)} 条，正向词命中 {pos_hits}、负向词命中 {neg_hits}，"
                f"情绪得分 {score:.1f}。"
            ),
            risk_tags=risks,
            source_refs=[f"{payload.get('source')}:{payload.get('metric')}"],
            stale=bool(payload.get("stale")),
        )
