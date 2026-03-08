"""News fusion service: fetch, process, link and export features."""

from __future__ import annotations

import copy
import hashlib
import time
from dataclasses import asdict
from typing import Any

from services.news_pipeline.fetchers.eastmoney_news_fetcher import EastmoneyNewsFetcher
from services.news_pipeline.fetchers.tavily_news_fetcher import TavilyNewsFetcher
from services.news_pipeline.processor import NewsProcessor
from services.news_pipeline.schema import NewsFeatureSummary, NewsItem


class NewsFusionService:
    """Orchestrate multi-source news pipeline."""

    def __init__(
        self,
        processor: NewsProcessor | None = None,
        eastmoney_fetcher: EastmoneyNewsFetcher | None = None,
        tavily_fetcher: TavilyNewsFetcher | None = None,
        source_manager: Any | None = None,
    ) -> None:
        self.processor = processor or NewsProcessor(time_window_hours=72)
        self.eastmoney_fetcher = eastmoney_fetcher or EastmoneyNewsFetcher()
        self.tavily_fetcher = tavily_fetcher or TavilyNewsFetcher()
        self.source_manager = source_manager
        self._last_collection_details: list[dict[str, Any]] = []

    def collect(self, limit: int = 50, tavily_query: str | None = None) -> dict[str, Any]:
        processed, source_stats, raw_count = self.collect_items(limit=limit, tavily_query=tavily_query)
        return {
            "raw_count": raw_count,
            "processed_count": len(processed),
            "dedup_removed": max(0, raw_count - len(processed)),
            "source_stats": source_stats,
            "items": [item.to_dict() for item in processed],
        }

    def collect_items(
        self,
        limit: int = 50,
        tavily_query: str | None = None,
    ) -> tuple[list[NewsItem], dict[str, int], int]:
        raw_items: list[NewsItem] = []
        source_stats: dict[str, int] = {}
        collection_details: list[dict[str, Any]] = []

        east_started = time.perf_counter()
        east_items: list[NewsItem] = []
        east_error: str | None = None
        try:
            east_items = self.eastmoney_fetcher.fetch(limit=limit)
        except Exception as exc:
            east_error = str(exc)
        east_latency = round((time.perf_counter() - east_started) * 1000, 2)
        raw_items.extend(east_items)
        source_stats["eastmoney"] = len(east_items)
        collection_details.append(
            {
                "source": "eastmoney",
                "status": "failed" if east_error else ("success" if east_items else "partial_success"),
                "latency_ms": east_latency,
                "fallback_source": None,
                "quality_score": 0.9 if east_items else (0.0 if east_error else 0.4),
                "error_message": east_error,
                "count": len(east_items),
            }
        )

        tavily_items: list[NewsItem] = []
        if self.tavily_fetcher.enabled:
            tavily_started = time.perf_counter()
            tavily_error: str | None = None
            try:
                tavily_items = self.tavily_fetcher.fetch(
                    query=tavily_query or "China ETF fund policy market",
                    limit=max(5, min(limit, 30)),
                    days=3,
                )
            except Exception as exc:
                tavily_error = str(exc)
            tavily_latency = round((time.perf_counter() - tavily_started) * 1000, 2)
            raw_items.extend(tavily_items)
            collection_details.append(
                {
                    "source": "tavily",
                    "status": "failed" if tavily_error else ("success" if tavily_items else "partial_success"),
                    "latency_ms": tavily_latency,
                    "fallback_source": None,
                    "quality_score": 0.85 if tavily_items else (0.0 if tavily_error else 0.4),
                    "error_message": tavily_error,
                    "count": len(tavily_items),
                }
            )
        else:
            collection_details.append(
                {
                    "source": "tavily",
                    "status": "not_requested",
                    "latency_ms": None,
                    "fallback_source": None,
                    "quality_score": None,
                    "error_message": "TAVILY_API_KEY not configured",
                    "count": 0,
                }
            )
        source_stats["tavily"] = len(tavily_items)
        processed = self.processor.process(raw_items)
        self._last_collection_details = collection_details
        return processed, source_stats, len(raw_items)

    def get_last_collection_details(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._last_collection_details)

    def symbol_news(self, symbol: str, items: list[NewsItem]) -> list[NewsItem]:
        return self.processor.related_for_symbol(items, symbol=symbol)

    def symbol_feature_summary(self, symbol: str, items: list[NewsItem]) -> NewsFeatureSummary:
        return self.processor.summarize_symbol_features(symbol=symbol, items=items)

    def build_factor_extra(
        self,
        symbol: str,
        items: list[NewsItem],
        *,
        source_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        summary = self.symbol_feature_summary(symbol=symbol, items=items)
        if summary.rows > 0 or self.source_manager is None:
            return {"news_feature": asdict(summary)}
        try:
            payload = self.source_manager.fetch_news(
                symbol=symbol,
                limit=20,
                bypass_cache=True,
                **dict(source_options or {}),
            )
            source_items = _payload_to_news_items(payload)
            if source_items:
                fallback_summary = self.processor.summarize_symbol_features(symbol=symbol, items=source_items)
                news_feature = asdict(fallback_summary)
                news_feature["fallback_source"] = payload.get("source")
                news_feature["fallback_mode"] = True
                return {"news_feature": news_feature}
        except Exception:
            pass
        return {"news_feature": asdict(summary)}


def _payload_to_news_items(payload: dict[str, Any]) -> list[NewsItem]:
    records = payload.get("records") or []
    output: list[NewsItem] = []
    for idx, row in enumerate(records):
        title = str(row.get("title") or row.get("content") or "").strip()
        content = str(row.get("content") or title).strip()
        published_at = str(row.get("event_time_utc") or row.get("time") or "")
        if not title or not published_at:
            continue
        digest = hashlib.sha1(f"{title}|{published_at}|{idx}".encode("utf-8")).hexdigest()[:20]
        output.append(
            NewsItem(
                uid=f"src_{digest}",
                title=title,
                content=content,
                published_at_utc=published_at,
                source=str(row.get("source") or payload.get("source") or "source_manager"),
                source_channel=str(payload.get("source") or "source_manager"),
                url=row.get("url"),
                relevance_score=float(row.get("relevance") or 0.5),
                raw={"metric": payload.get("metric"), "fallback_mode": (payload.get("metadata") or {}).get("fallback_mode")},
            )
        )
    return output
