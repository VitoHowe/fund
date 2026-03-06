"""Unit tests for news pipeline."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from services.news_pipeline.processor import NewsProcessor
from services.news_pipeline.schema import NewsItem


class NewsPipelineTests(unittest.TestCase):
    def test_dedup_and_entity_linking(self) -> None:
        now = datetime.now(timezone.utc)
        item_1 = NewsItem(
            uid="a1",
            title="鹏华中证细分化工产业主题ETF联接C 获政策利好",
            content="化工ETF 资金净流入。",
            published_at_utc=now.isoformat(),
            source="财联社",
            source_channel="eastmoney",
        )
        item_2 = NewsItem(
            uid="a2",
            title="鹏华中证细分化工产业主题ETF联接C 获政策利好",
            content="化工ETF 资金净流入。",
            published_at_utc=now.isoformat(),
            source="财联社",
            source_channel="eastmoney",
        )
        processor = NewsProcessor(time_window_hours=72)
        processed = processor.process([item_1, item_2], now_utc=now)
        self.assertEqual(len(processed), 1)
        self.assertIn("014943", processed[0].symbols)
        self.assertIn("化工", processed[0].sectors)

    def test_time_window_filter(self) -> None:
        now = datetime.now(timezone.utc)
        old_item = NewsItem(
            uid="old",
            title="旧新闻",
            content="历史内容",
            published_at_utc=(now - timedelta(hours=100)).isoformat(),
            source="新浪",
            source_channel="eastmoney",
        )
        recent_item = NewsItem(
            uid="new",
            title="新新闻",
            content="最新内容",
            published_at_utc=now.isoformat(),
            source="新浪",
            source_channel="eastmoney",
        )
        processor = NewsProcessor(time_window_hours=72)
        processed = processor.process([old_item, recent_item], now_utc=now)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0].uid, "new")


if __name__ == "__main__":
    unittest.main()

