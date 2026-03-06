"""News fusion service: fetch, process, link and export features."""

from __future__ import annotations

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
    ) -> None:
        self.processor = processor or NewsProcessor(time_window_hours=72)
        self.eastmoney_fetcher = eastmoney_fetcher or EastmoneyNewsFetcher()
        self.tavily_fetcher = tavily_fetcher or TavilyNewsFetcher()

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
        east_items = self.eastmoney_fetcher.fetch(limit=limit)
        raw_items.extend(east_items)
        source_stats["eastmoney"] = len(east_items)
        tavily_items: list[NewsItem] = []
        if self.tavily_fetcher.enabled:
            tavily_items = self.tavily_fetcher.fetch(
                query=tavily_query or "China ETF fund policy market",
                limit=max(5, min(limit, 30)),
                days=3,
            )
            raw_items.extend(tavily_items)
        source_stats["tavily"] = len(tavily_items)
        processed = self.processor.process(raw_items)
        return processed, source_stats, len(raw_items)

    def symbol_news(self, symbol: str, items: list[NewsItem]) -> list[NewsItem]:
        return self.processor.related_for_symbol(items, symbol=symbol)

    def symbol_feature_summary(self, symbol: str, items: list[NewsItem]) -> NewsFeatureSummary:
        return self.processor.summarize_symbol_features(symbol=symbol, items=items)

    def build_factor_extra(self, symbol: str, items: list[NewsItem]) -> dict[str, Any]:
        summary = self.symbol_feature_summary(symbol=symbol, items=items)
        return {"news_feature": asdict(summary)}
