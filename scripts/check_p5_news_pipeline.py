"""P5 validation: news and international dynamic fusion pipeline."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.data_hub import build_default_source_manager
from services.factor_engine import FactorScorer, WeightTemplateManager, build_default_factor_registry
from services.news_pipeline import NewsFusionService
from services.news_pipeline.schema import NewsItem


def _fallback_items_from_source_manager(limit: int = 30) -> list[NewsItem]:
    manager = build_default_source_manager()
    payload = manager.fetch_news(symbol=None, limit=limit, bypass_cache=True)
    rows = payload.get("records") or []
    out: list[NewsItem] = []
    for idx, row in enumerate(rows):
        out.append(
            NewsItem(
                uid=f"fallback_{idx}",
                title=str(row.get("title") or ""),
                content=str(row.get("content") or row.get("title") or ""),
                published_at_utc=str(row.get("event_time_utc") or datetime.now(timezone.utc).isoformat()),
                source=str(row.get("source") or payload.get("source") or "fallback"),
                source_channel=str(payload.get("source") or "fallback"),
                url=row.get("url"),
                raw={"fallback": True},
            )
        )
    return out


def main() -> None:
    fusion = NewsFusionService()
    raw_external_ok = True
    try:
        raw_items, source_stats, raw_count = fusion.collect_items(limit=50)
    except Exception:
        raw_external_ok = False
        raw_items = _fallback_items_from_source_manager(limit=30)
        source_stats = {"eastmoney": 0, "tavily": 0, "fallback": len(raw_items)}
        raw_count = len(raw_items)
    if not raw_items:
        raw_external_ok = False
        raw_items = _fallback_items_from_source_manager(limit=30)
        source_stats["fallback"] = len(raw_items)
        raw_count = len(raw_items)

    now_iso = datetime.now(timezone.utc).isoformat()
    injected = NewsItem(
        uid="injected_014943_1",
        title="鹏华中证细分化工产业主题ETF联接C 获政策利好",
        content="监管政策提振化工板块，资金净流入，化工ETF 热度回暖。",
        published_at_utc=now_iso,
        source="local_injected",
        source_channel="test",
    )
    injected_dup = NewsItem(
        uid="injected_014943_2",
        title="鹏华中证细分化工产业主题ETF联接C 获政策利好",
        content="监管政策提振化工板块，资金净流入，化工ETF 热度回暖。",
        published_at_utc=now_iso,
        source="local_injected",
        source_channel="test",
    )
    processed = fusion.processor.process(raw_items + [injected, injected_dup])
    related = fusion.symbol_news("014943", processed)
    summary = fusion.symbol_feature_summary("014943", related)

    scorer = FactorScorer(
        source_manager=build_default_source_manager(),
        registry=build_default_factor_registry(),
        weight_manager=WeightTemplateManager(config_path=str(ROOT / "config" / "factor_weights.yaml")),
    )
    card = scorer.score_symbol(
        symbol="014943",
        market_state="neutral",
        proxy_symbol="159870",
        extra_context=fusion.build_factor_extra("014943", related),
    ).to_dict()
    sentiment_factor = (card.get("factor_scores") or {}).get("sentiment") or {}
    output = {
        "symbol": "014943",
        "checks": {
            "news_fetch_and_parse_stable": len(raw_items) > 0,
            "news_fetch_direct_external_ok": raw_external_ok,
            "dedup_effective": len(processed) < len(raw_items) + 2,
            "symbol_news_query_available": len(related) > 0,
            "symbol_sentiment_available": summary.rows > 0,
            "sentiment_written_to_factor_input": sentiment_factor.get("source_refs") == [
                "news_pipeline:feature_summary"
            ],
        },
        "stats": {
            "source_stats": source_stats,
            "raw_count": raw_count,
            "processed_count": len(processed),
            "related_count": len(related),
            "dedup_removed": (len(raw_items) + 2) - len(processed),
        },
        "news_feature_summary": summary.to_dict(),
        "sentiment_factor": sentiment_factor,
        "scorecard_snapshot": {
            "total_score": card.get("total_score"),
            "confidence": card.get("confidence"),
            "weight_version": card.get("weight_version"),
            "risk_tags": card.get("risk_tags"),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
