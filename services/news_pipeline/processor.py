"""News cleaning, dedup, entity linking and feature aggregation."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from services.news_pipeline.schema import NewsFeatureSummary, NewsItem
from services.news_pipeline.sentiment import score_sentiment


SOURCE_TIER = {
    "新华社": "A",
    "人民日报": "A",
    "财联社": "A",
    "新浪": "B",
    "东方财富": "B",
    "eastmoney_fastnews": "B",
    "cls": "A",
    "tavily": "C",
}

TIER_WEIGHT = {"A": 1.0, "B": 0.7, "C": 0.4}


class NewsProcessor:
    """Pipeline for normalize -> dedup -> sentiment -> entity linking."""

    def __init__(
        self,
        time_window_hours: int = 72,
        symbol_aliases: dict[str, list[str]] | None = None,
        sector_aliases: dict[str, list[str]] | None = None,
    ) -> None:
        self.time_window_hours = max(1, int(time_window_hours))
        self.symbol_aliases = symbol_aliases or {
            "014943": ["014943", "鹏华中证细分化工产业主题ETF联接C", "鹏华中证细分化工"],
            "159870": ["159870", "化工ETF", "细分化工"],
        }
        self.sector_aliases = sector_aliases or {
            "化工": ["化工", "新材料", "煤化工", "石化"],
            "新能源": ["新能源", "光伏", "储能", "锂电"],
            "半导体": ["半导体", "芯片", "集成电路"],
        }

    def process(self, items: list[NewsItem], now_utc: datetime | None = None) -> list[NewsItem]:
        now_utc = now_utc or datetime.now(timezone.utc)
        floor = now_utc - timedelta(hours=self.time_window_hours)
        filtered = [item for item in items if self._is_in_window(item, floor)]
        unique: dict[str, NewsItem] = {}
        for item in filtered:
            normalized_title = _normalize_text(item.title)
            normalized_content = _normalize_text(item.content)
            fingerprint = hashlib.sha1(f"{normalized_title}|{normalized_content}".encode("utf-8")).hexdigest()
            if fingerprint in unique:
                # Keep the latest one if duplicated.
                if item.published_at_utc > unique[fingerprint].published_at_utc:
                    unique[fingerprint] = item
                continue
            unique[fingerprint] = item
        processed: list[NewsItem] = []
        for item in unique.values():
            text = f"{item.title} {item.content}".strip()
            score, label, detail = score_sentiment(text)
            symbols, sectors, relevance = self._link_entities(text)
            tier = self._infer_tier(item.source)
            item.sentiment_score = score
            item.sentiment_label = label
            item.symbols = symbols
            item.sectors = sectors
            item.relevance_score = relevance
            item.credibility_tier = tier
            raw = dict(item.raw)
            raw["sentiment_detail"] = detail
            item.raw = raw
            processed.append(item)
        processed.sort(key=lambda row: row.published_at_utc, reverse=True)
        return processed

    def related_for_symbol(self, items: list[NewsItem], symbol: str) -> list[NewsItem]:
        alias = self.symbol_aliases.get(symbol, [symbol])
        alias = [text for text in alias if text]
        out: list[NewsItem] = []
        for item in items:
            blob = f"{item.title} {item.content}"
            if symbol in item.symbols:
                out.append(item)
                continue
            if any(token in blob for token in alias):
                out.append(item)
        return out

    def summarize_symbol_features(self, symbol: str, items: list[NewsItem]) -> NewsFeatureSummary:
        if not items:
            return NewsFeatureSummary(
                symbol=symbol,
                rows=0,
                avg_sentiment=0.0,
                positive_ratio=0.0,
                negative_ratio=0.0,
                credibility_weighted_sentiment=0.0,
                latest_news_time_utc=None,
                tags=["NO_NEWS"],
            )
        rows = len(items)
        score_sum = sum(item.sentiment_score for item in items)
        pos_count = sum(1 for item in items if item.sentiment_label == "positive")
        neg_count = sum(1 for item in items if item.sentiment_label == "negative")
        weighted_num = 0.0
        weighted_den = 0.0
        for item in items:
            weight = TIER_WEIGHT.get(item.credibility_tier, 0.5)
            weighted_num += item.sentiment_score * weight
            weighted_den += weight
        weighted_sent = weighted_num / weighted_den if weighted_den > 0 else 0.0
        tags: list[str] = []
        if weighted_sent > 0.2:
            tags.append("NEWS_BULLISH")
        elif weighted_sent < -0.2:
            tags.append("NEWS_BEARISH")
        if any(item.credibility_tier == "A" for item in items):
            tags.append("HAS_TOP_TIER_SOURCE")
        latest = max(item.published_at_utc for item in items)
        return NewsFeatureSummary(
            symbol=symbol,
            rows=rows,
            avg_sentiment=round(score_sum / rows, 4),
            positive_ratio=round(pos_count / rows, 4),
            negative_ratio=round(neg_count / rows, 4),
            credibility_weighted_sentiment=round(weighted_sent, 4),
            latest_news_time_utc=latest,
            tags=tags,
        )

    def _is_in_window(self, item: NewsItem, floor: datetime) -> bool:
        try:
            ts = datetime.fromisoformat(item.published_at_utc.replace("Z", "+00:00"))
        except ValueError:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc) >= floor

    def _link_entities(self, text: str) -> tuple[list[str], list[str], float]:
        symbols: list[str] = []
        sectors: list[str] = []
        relevance = 0.0
        for symbol, aliases in self.symbol_aliases.items():
            if any(alias and alias in text for alias in aliases):
                symbols.append(symbol)
                relevance += 0.5
        for sector, aliases in self.sector_aliases.items():
            if any(alias and alias in text for alias in aliases):
                sectors.append(sector)
                relevance += 0.3
        relevance = min(1.0, relevance)
        return symbols, sectors, relevance

    @staticmethod
    def _infer_tier(source: str) -> str:
        for key, tier in SOURCE_TIER.items():
            if key in (source or ""):
                return tier
        return "B"


def _normalize_text(text: str) -> str:
    trimmed = re.sub(r"\s+", " ", (text or "").strip())
    return trimmed.lower()

