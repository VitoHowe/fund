"""Rule-based sentiment scoring for finance news."""

from __future__ import annotations

from typing import Any


POSITIVE_TOKENS = (
    "利好",
    "增长",
    "上调",
    "回暖",
    "提振",
    "突破",
    "增持",
    "净流入",
    "超预期",
    "扩张",
)

NEGATIVE_TOKENS = (
    "利空",
    "下滑",
    "下调",
    "风险",
    "回撤",
    "减持",
    "净流出",
    "承压",
    "不及预期",
    "收缩",
)

POLICY_TOKENS = (
    "国务院",
    "证监会",
    "央行",
    "发改委",
    "财政部",
    "政策",
    "监管",
)


def score_sentiment(text: str) -> tuple[float, str, dict[str, Any]]:
    """Return sentiment score in [-1, 1], label and diagnostics."""
    content = (text or "").strip()
    if not content:
        return 0.0, "neutral", {"positive_hits": 0, "negative_hits": 0, "policy_hits": 0}
    pos_hits = sum(1 for token in POSITIVE_TOKENS if token in content)
    neg_hits = sum(1 for token in NEGATIVE_TOKENS if token in content)
    policy_hits = sum(1 for token in POLICY_TOKENS if token in content)
    denom = max(pos_hits + neg_hits, 1)
    raw = (pos_hits - neg_hits) / denom
    policy_boost = min(policy_hits * 0.05, 0.2)
    score = max(-1.0, min(1.0, raw + (policy_boost if raw >= 0 else -policy_boost)))
    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"
    return score, label, {
        "positive_hits": pos_hits,
        "negative_hits": neg_hits,
        "policy_hits": policy_hits,
        "raw_score": raw,
        "policy_boost": policy_boost,
    }

