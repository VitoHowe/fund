"""Eastmoney fast-news fetcher."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from services.news_pipeline.schema import NewsItem


SH_TZ = ZoneInfo("Asia/Shanghai")


class EastmoneyNewsFetcher:
    """Fetch fast news from Eastmoney np-weblist endpoint."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://kuaixun.eastmoney.com/",
        }

    def fetch(self, limit: int = 50, timeout_seconds: int = 15) -> list[NewsItem]:
        url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        params = {
            "req_trace": str(int(time.time() * 1000)),
            "client": "web",
            "biz": "web_news_col",
            "order": "1",
            "pn": "1",
            "pz": str(max(1, min(limit, 200))),
        }
        resp = self.session.get(url, headers=self.headers, params=params, timeout=timeout_seconds)
        resp.raise_for_status()
        payload = resp.json()
        rows = ((payload.get("data") or {}).get("fastNewsList") or [])
        output: list[NewsItem] = []
        for row in rows:
            title = str(row.get("title") or row.get("digest") or row.get("content") or "").strip()
            content = str(row.get("content") or row.get("digest") or title).strip()
            showtime = row.get("showtime") or row.get("time")
            published_at_utc = _to_utc_iso(showtime)
            source_name = str(row.get("media") or "eastmoney_fastnews")
            url = row.get("url")
            digest = hashlib.sha1(f"{title}|{content}|{published_at_utc}".encode("utf-8")).hexdigest()[:20]
            output.append(
                NewsItem(
                    uid=f"em_{digest}",
                    title=title,
                    content=content,
                    published_at_utc=published_at_utc,
                    source=source_name,
                    source_channel="eastmoney",
                    url=url,
                    raw={"showtime": showtime, "code": row.get("code")},
                )
            )
        return output


def _to_utc_iso(value: Any) -> str:
    if value in (None, "", "--"):
        return datetime.now(timezone.utc).isoformat()
    text = str(value).strip().replace("/", "-")
    parsed: datetime | None = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc).isoformat()
    if parsed.tzinfo is None:
        # Eastmoney fast news timestamps are Shanghai local time.
        parsed = parsed.replace(tzinfo=SH_TZ)
    return parsed.astimezone(timezone.utc).isoformat()
