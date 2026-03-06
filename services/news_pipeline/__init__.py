"""News pipeline exports."""

from services.news_pipeline.processor import NewsProcessor
from services.news_pipeline.schema import NewsFeatureSummary, NewsItem
from services.news_pipeline.service import NewsFusionService

__all__ = ["NewsProcessor", "NewsItem", "NewsFeatureSummary", "NewsFusionService"]

