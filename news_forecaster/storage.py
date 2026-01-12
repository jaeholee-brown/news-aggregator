"""JSON file storage management for news snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

from .models import NewsSnapshot, QuestionMetadata

T = TypeVar("T", bound=BaseModel)


class Storage:
    """Manages JSON file storage for questions and news."""

    def __init__(self, data_dir: Path | str = "data"):
        self.data_dir = Path(data_dir)
        self.questions_dir = self.data_dir / "questions"
        self.news_dir = self.data_dir / "news"
        self.series_dir = self.data_dir / "series"

        # Ensure directories exist
        for dir_path in [self.questions_dir, self.news_dir, self.series_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _get_timestamp_filename(self, dt: datetime) -> str:
        """Convert datetime to filesystem-safe filename."""
        return dt.strftime("%Y-%m-%dT%H-%M-%S") + ".json"

    def _save_model(self, path: Path, model: BaseModel) -> None:
        """Save a Pydantic model to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(model.model_dump_json(indent=2))

    def _load_model(self, path: Path, model_class: Type[T]) -> Optional[T]:
        """Load a Pydantic model from JSON file."""
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return model_class.model_validate(data)

    # Question methods
    def save_question(self, question: QuestionMetadata) -> None:
        """Save question metadata."""
        path = self.questions_dir / f"{question.question_id}.json"
        self._save_model(path, question)

    def load_question(self, question_id: int) -> Optional[QuestionMetadata]:
        """Load question metadata."""
        path = self.questions_dir / f"{question_id}.json"
        return self._load_model(path, QuestionMetadata)

    # News methods
    def save_news(self, question_id: int, snapshot: NewsSnapshot) -> None:
        """Save news snapshot with timestamp and update latest."""
        question_news_dir = self.news_dir / str(question_id)
        question_news_dir.mkdir(parents=True, exist_ok=True)

        # Save timestamped version
        timestamp_file = question_news_dir / self._get_timestamp_filename(snapshot.fetched_at)
        self._save_model(timestamp_file, snapshot)

        # Update latest.json
        latest_file = question_news_dir / "latest.json"
        self._save_model(latest_file, snapshot)

    def load_latest_news(self, question_id: int) -> Optional[NewsSnapshot]:
        """Load most recent news snapshot."""
        path = self.news_dir / str(question_id) / "latest.json"
        return self._load_model(path, NewsSnapshot)

    def load_news_history(self, question_id: int) -> list[NewsSnapshot]:
        """Load all historical news snapshots, sorted by date (newest first)."""
        question_news_dir = self.news_dir / str(question_id)
        if not question_news_dir.exists():
            return []

        snapshots = []
        for path in question_news_dir.glob("*.json"):
            if path.name == "latest.json":
                continue
            snapshot = self._load_model(path, NewsSnapshot)
            if snapshot:
                snapshots.append(snapshot)

        return sorted(snapshots, key=lambda s: s.fetched_at, reverse=True)

    # Series methods
    def save_series(self, series_id: int, question_ids: list[int]) -> None:
        """Save mapping of series to question IDs."""
        path = self.series_dir / f"{series_id}.json"
        with open(path, "w") as f:
            json.dump({"series_id": series_id, "question_ids": question_ids}, f, indent=2)

    def load_series(self, series_id: int) -> Optional[list[int]]:
        """Load question IDs for a series."""
        path = self.series_dir / f"{series_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return data.get("question_ids", [])

    # Utility methods
    def cleanup_old_snapshots(self, question_id: int, keep_days: int = 30) -> int:
        """Remove news snapshots older than keep_days. Returns count of removed files."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        removed = 0

        news_dir = self.news_dir / str(question_id)
        if not news_dir.exists():
            return 0

        for path in news_dir.glob("*.json"):
            if path.name == "latest.json":
                continue
            try:
                # Parse timestamp from filename
                timestamp_str = path.stem
                file_dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H-%M-%S")
                if file_dt < cutoff:
                    path.unlink()
                    removed += 1
            except ValueError:
                continue

        return removed
