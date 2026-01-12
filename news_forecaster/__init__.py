"""
News Aggregator - A human-facing news aggregation and change detection tool.

This package fetches questions from Metaculus, aggregates related news using Exa AI,
detects significant changes, and sends email notifications when important news
developments occur.
"""

from .config import Config
from .models import (
    QuestionMetadata,
    NewsArticle,
    NewsSnapshot,
    ChangeReport,
    NewsUpdate,
)
from .metaculus_client import MetaculusClient
from .news_aggregator import NewsAggregator
from .change_detector import ChangeDetector
from .email_notifier import EmailNotifier
from .storage import Storage

__all__ = [
    "Config",
    "QuestionMetadata",
    "NewsArticle",
    "NewsSnapshot",
    "ChangeReport",
    "NewsUpdate",
    "MetaculusClient",
    "NewsAggregator",
    "ChangeDetector",
    "EmailNotifier",
    "Storage",
]
