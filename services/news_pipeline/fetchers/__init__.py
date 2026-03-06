"""News fetchers."""

from services.news_pipeline.fetchers.eastmoney_news_fetcher import EastmoneyNewsFetcher
from services.news_pipeline.fetchers.tavily_news_fetcher import TavilyNewsFetcher

__all__ = ["EastmoneyNewsFetcher", "TavilyNewsFetcher"]

