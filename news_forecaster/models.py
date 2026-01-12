"""Pydantic data models for the news aggregator."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class QuestionMetadata(BaseModel):
    """Metadata for a Metaculus question."""

    question_id: int
    post_id: int
    title: str
    question_type: Literal["binary", "numeric", "multiple_choice", "discrete"]
    resolution_criteria: str
    fine_print: Optional[str] = None
    background_info: str
    scheduled_close_time: Optional[datetime] = None
    page_url: str
    series_id: Optional[int] = None
    last_fetched: datetime

    # Additional fields for numeric questions
    unit_of_measure: Optional[str] = None
    upper_bound: Optional[float] = None
    lower_bound: Optional[float] = None
    open_upper_bound: Optional[bool] = None
    open_lower_bound: Optional[bool] = None
    zero_point: Optional[float] = None

    # For multiple choice questions
    options: Optional[list[str]] = None


class NewsArticle(BaseModel):
    """A single news article."""

    url: str
    title: str
    summary: str
    full_text: Optional[str] = None
    published_date: Optional[datetime] = None
    source: str
    relevance_score: Optional[float] = None


class NewsSnapshot(BaseModel):
    """A collection of news articles fetched at a point in time."""

    question_id: int
    fetched_at: datetime
    articles: list[NewsArticle]
    search_query: str
    snapshot_id: str = ""  # Will be set to timestamp string

    def model_post_init(self, __context) -> None:
        """Set snapshot_id from fetched_at if not provided."""
        if not self.snapshot_id:
            self.snapshot_id = self.fetched_at.strftime("%Y-%m-%dT%H-%M-%S")


class ChangeReport(BaseModel):
    """Report on changes detected between news snapshots."""

    question_id: int
    detected_at: datetime
    previous_snapshot_id: str
    current_snapshot_id: str
    change_summary: str
    significance_score: float = Field(ge=0.0, le=1.0)
    is_significant: bool
    new_articles: list[NewsArticle]


class NewsUpdate(BaseModel):
    """A complete update containing question, news, and change info."""

    question: QuestionMetadata
    news_snapshot: NewsSnapshot
    change_report: Optional[ChangeReport] = None
