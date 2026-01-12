"""Configuration management for the news forecaster."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import dotenv

dotenv.load_dotenv()


@dataclass
class Config:
    """Configuration loaded from environment variables."""

    # Metaculus API
    metaculus_token: Optional[str] = None

    # News aggregation
    exa_api_key: Optional[str] = None
    firecrawl_api_key: Optional[str] = None

    # LLM APIs
    openai_api_key: Optional[str] = None

    # Email notifications
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    email_recipients: list[str] = field(default_factory=list)

    # Questions to track
    question_ids: list[int] = field(default_factory=list)
    series_ids: list[int] = field(default_factory=list)

    # Data storage
    data_dir: Path = field(default_factory=lambda: Path("data"))

    # LLM model for change detection
    change_detection_model: str = "gpt-5-mini"

    # Thresholds
    significance_threshold: float = 0.2  # News change significance threshold
    min_content_length: int = 500  # Minimum chars before Firecrawl fallback

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        # Parse comma-separated lists
        email_recipients = []
        if recipients_str := os.getenv("EMAIL_RECIPIENTS"):
            email_recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

        question_ids = []
        if qids_str := os.getenv("QUESTION_IDS"):
            question_ids = [int(q.strip()) for q in qids_str.split(",") if q.strip()]

        series_ids = []
        if sids_str := os.getenv("SERIES_IDS"):
            series_ids = [int(s.strip()) for s in sids_str.split(",") if s.strip()]

        # Data directory
        data_dir = Path(os.getenv("DATA_DIR", "data"))

        # Significance threshold (configurable via env)
        significance_threshold = float(os.getenv("SIGNIFICANCE_THRESHOLD", "0.2"))

        return cls(
            metaculus_token=os.getenv("METACULUS_TOKEN"),
            exa_api_key=os.getenv("EXA_API_KEY"),
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            gmail_user=os.getenv("GMAIL_USER"),
            gmail_app_password=os.getenv("GMAIL_APP_PASSWORD"),
            email_recipients=email_recipients,
            question_ids=question_ids,
            series_ids=series_ids,
            data_dir=data_dir,
            change_detection_model=os.getenv("CHANGE_DETECTION_MODEL", "gpt-5-mini"),
            significance_threshold=significance_threshold,
        )

    def validate(self) -> list[str]:
        """Validate that required configuration is present. Returns list of missing items."""
        missing = []

        if not self.exa_api_key:
            missing.append("EXA_API_KEY")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.question_ids and not self.series_ids:
            missing.append("QUESTION_IDS or SERIES_IDS (at least one required)")

        return missing
