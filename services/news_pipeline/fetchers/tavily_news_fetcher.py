"""Optional Tavily fetcher for external finance news."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import requests

from services.news_pipeline.schema import NewsItem


class TavilyNewsFetcher:
    """Fetch finance news from Tavily search API when API key is configured."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.endpoint = "https://api.tavily.com/search"
        self.session = requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def fetch(
        self,
        query: str = "China ETF fund policy market",
        limit: int = 20,
        days: int = 3,
        timeout_seconds: int = 20,
    ) -> list[NewsItem]:
        if not self.enabled:
            return []
        payload = {
            "api_key": self.api_key,
            "query": query,
            "topic": "news",
            "time_range": f"{max(1, int(days))}d",
            "search_depth": "basic",
            "max_results": max(1, min(limit, 50)),
            "include_raw_content": False,
        }
        resp = self.session.post(self.endpoint, json=payload, timeout=timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("results") or []
        out: list[NewsItem] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            content = str(row.get("content") or "").strip()
            url = row.get("url")
            published = _to_utc_iso(row.get("published_date"))
            source_name = str(row.get("source") or "tavily")
            digest = hashlib.sha1(f"{title}|{content}|{published}".encode("utf-8")).hexdigest()[:20]
            out.append(
                NewsItem(
                    uid=f"tv_{digest}",
                    title=title,
                    content=content,
                    published_at_utc=published,
                    source=source_name,
                    source_channel="tavily",
                    url=url,
                    raw={"score": row.get("score")},
                )
            )
        return out


def _to_utc_iso(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()

