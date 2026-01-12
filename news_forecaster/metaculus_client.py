"""Read-only Metaculus API client for fetching questions."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import requests

from .models import QuestionMetadata


class MetaculusClient:
    """Read-only Metaculus API client with rate limiting."""

    BASE_URL = "https://www.metaculus.com/api"

    # Rate limiting: ~1 request per second with exponential backoff on 429
    MIN_REQUEST_INTERVAL = 1.0  # seconds between requests
    MAX_RETRIES = 5
    INITIAL_BACKOFF = 2.0  # seconds

    def __init__(self, token: Optional[str] = None):
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Token {token}"
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Ensure minimum time between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            sleep_time = self.MIN_REQUEST_INTERVAL - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _request_with_retry(
        self, url: str, params: Optional[dict] = None
    ) -> Optional[requests.Response]:
        """Make a request with rate limiting and exponential backoff on 429."""
        for attempt in range(self.MAX_RETRIES):
            self._rate_limit()
            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code == 429:
                # Rate limited - exponential backoff
                backoff = self.INITIAL_BACKOFF * (2 ** attempt)
                print(f"Rate limited (429). Waiting {backoff:.1f}s before retry...")
                time.sleep(backoff)
                continue

            return response

        print(f"Max retries ({self.MAX_RETRIES}) exceeded for {url}")
        return None

    def get_question(self, question_id: int) -> Optional[QuestionMetadata]:
        """Fetch a single question by post ID."""
        url = f"{self.BASE_URL}/posts/{question_id}/"
        response = self._request_with_retry(url)

        if response is None:
            return None

        if not response.ok:
            print(f"Failed to fetch question {question_id}: {response.status_code}")
            return None

        return self._parse_post_response(response.json())

    def get_question_by_question_id(self, question_id: int) -> Optional[QuestionMetadata]:
        """Fetch a question using the questions endpoint."""
        url = f"{self.BASE_URL}2/questions/{question_id}/"
        response = self._request_with_retry(url)

        if response is None:
            return None

        if not response.ok:
            print(f"Failed to fetch question {question_id}: {response.status_code}")
            return None

        data = response.json()
        return self._parse_question_data(data, data.get("id", question_id))

    def get_questions_in_series(self, series_id: int) -> list[QuestionMetadata]:
        """Fetch all questions in a series/project."""
        url = f"{self.BASE_URL}/posts/"
        params = {
            "project": series_id,
            "limit": 100,
            "include_description": "true",
        }

        response = self._request_with_retry(url, params)

        if response is None:
            print(f"Failed to fetch series {series_id} after retries")
            return []

        if not response.ok:
            print(f"Failed to fetch series {series_id}: {response.status_code}")
            return []

        data = response.json()
        questions = []

        for post in data.get("results", []):
            question_meta = self._parse_post_response(post, series_id=series_id)
            if question_meta:
                questions.append(question_meta)

        return questions

    def _parse_post_response(
        self, data: dict, series_id: Optional[int] = None
    ) -> Optional[QuestionMetadata]:
        """Parse a post response into QuestionMetadata."""
        question = data.get("question", {})
        if not question:
            return None

        return self._parse_question_data(question, data.get("id"), series_id)

    def _parse_question_data(
        self, question: dict, post_id: int, series_id: Optional[int] = None
    ) -> QuestionMetadata:
        """Parse question data into QuestionMetadata."""
        scaling = question.get("scaling", {}) or {}

        # Parse options for multiple choice
        options = None
        if question.get("type") == "multiple_choice":
            options = question.get("options", [])

        # Parse scheduled close time
        scheduled_close_time = None
        if close_str := question.get("scheduled_close_time"):
            try:
                scheduled_close_time = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return QuestionMetadata(
            question_id=question.get("id", post_id),
            post_id=post_id,
            title=question.get("title", ""),
            question_type=question.get("type", "binary"),
            resolution_criteria=question.get("resolution_criteria", ""),
            fine_print=question.get("fine_print"),
            background_info=question.get("description", ""),
            scheduled_close_time=scheduled_close_time,
            page_url=f"https://www.metaculus.com/questions/{post_id}/",
            series_id=series_id,
            last_fetched=datetime.now(timezone.utc),
            unit_of_measure=question.get("unit"),
            upper_bound=scaling.get("range_max"),
            lower_bound=scaling.get("range_min"),
            open_upper_bound=question.get("open_upper_bound"),
            open_lower_bound=question.get("open_lower_bound"),
            zero_point=scaling.get("zero_point"),
            options=options,
        )
