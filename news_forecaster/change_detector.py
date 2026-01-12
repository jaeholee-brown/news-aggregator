"""Detects significant changes in news between snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

from .models import ChangeReport, NewsArticle, NewsSnapshot, QuestionMetadata

# Change detection prompt for the smaller LLM
CHANGE_DETECTION_PROMPT = """
You are analyzing news changes for a forecasting question.

Question: {question_title}
Resolution Criteria: {resolution_criteria}

Previous news summary (from {previous_date}):
{previous_summary}

New articles since then:
{new_articles}

Analyze whether these new articles represent a SIGNIFICANT change that would:
1. Materially affect the probability of the question's outcome
2. Introduce new key information that wasn't previously available
3. Change the status quo assumption

Respond with ONLY a JSON object in this exact format (no other text):
{{
    "SIGNIFICANCE_SCORE": <number from 0.0 to 1.0>,
    "IS_SIGNIFICANT": <true if score > 0.3, false otherwise>,
    "CHANGE_SUMMARY": "<2-3 sentence summary of what changed and why it matters>"
}}
"""


class ChangeDetector:
    """Detects significant changes in news using GPT-5-mini."""

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-5-mini",
        significance_threshold: float = 0.3,
    ):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.significance_threshold = significance_threshold

    async def detect_changes(
        self,
        question: QuestionMetadata,
        previous_snapshot: NewsSnapshot,
        current_snapshot: NewsSnapshot,
    ) -> ChangeReport:
        """
        Detect significant changes between two news snapshots.

        Args:
            question: The question context
            previous_snapshot: The previous news snapshot
            current_snapshot: The current news snapshot

        Returns:
            ChangeReport with analysis of the changes
        """
        # Find genuinely new articles
        previous_urls = {a.url for a in previous_snapshot.articles}
        new_articles = [a for a in current_snapshot.articles if a.url not in previous_urls]

        # If no new articles, return a no-change report
        if not new_articles:
            return ChangeReport(
                question_id=question.question_id,
                detected_at=datetime.now(timezone.utc),
                previous_snapshot_id=previous_snapshot.snapshot_id,
                current_snapshot_id=current_snapshot.snapshot_id,
                change_summary="No new articles found since last check.",
                significance_score=0.0,
                is_significant=False,
                new_articles=[],
            )

        # Summarize previous news
        previous_summary = self._summarize_articles(previous_snapshot.articles[:10])

        # Format new articles
        new_articles_text = self._format_articles(new_articles[:10])

        # Call LLM for change detection
        prompt = CHANGE_DETECTION_PROMPT.format(
            question_title=question.title,
            resolution_criteria=question.resolution_criteria or "",
            previous_date=previous_snapshot.fetched_at.strftime("%Y-%m-%d %H:%M"),
            previous_summary=previous_summary,
            new_articles=new_articles_text,
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            # Note: gpt-5-mini only supports default temperature (1)
        )

        result_text = response.choices[0].message.content or "{}"

        # Parse JSON response
        try:
            # Try to extract JSON from the response
            result = self._parse_json_response(result_text)
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback if JSON parsing fails
            print(f"Failed to parse change detection response: {e}")
            result = {
                "SIGNIFICANCE_SCORE": 0.5,
                "IS_SIGNIFICANT": True,
                "CHANGE_SUMMARY": f"New articles found but analysis failed: {len(new_articles)} new article(s)",
            }

        significance_score = float(result.get("SIGNIFICANCE_SCORE", 0.0))
        is_significant = (
            result.get("IS_SIGNIFICANT", False)
            or significance_score > self.significance_threshold
        )

        return ChangeReport(
            question_id=question.question_id,
            detected_at=datetime.now(timezone.utc),
            previous_snapshot_id=previous_snapshot.snapshot_id,
            current_snapshot_id=current_snapshot.snapshot_id,
            change_summary=result.get("CHANGE_SUMMARY", "No summary available."),
            significance_score=significance_score,
            is_significant=is_significant,
            new_articles=new_articles,
        )

    def _summarize_articles(self, articles: list[NewsArticle]) -> str:
        """Create a brief summary of articles for the prompt."""
        if not articles:
            return "No previous articles."

        summaries = []
        for article in articles[:10]:
            pub_date = (
                article.published_date.strftime("%Y-%m-%d")
                if article.published_date
                else "Unknown"
            )
            summary = f"- [{pub_date}] {article.title}"
            if article.summary:
                summary += f": {article.summary[:150]}..."
            summaries.append(summary)

        return "\n".join(summaries)

    def _format_articles(self, articles: list[NewsArticle]) -> str:
        """Format articles for the change detection prompt."""
        if not articles:
            return "No new articles."

        formatted = []
        for i, article in enumerate(articles, 1):
            pub_date = (
                article.published_date.strftime("%Y-%m-%d")
                if article.published_date
                else "Unknown"
            )
            text = f"[{i}] {article.title}\n"
            text += f"    Source: {article.source}, Date: {pub_date}\n"
            if article.summary:
                text += f"    Summary: {article.summary[:300]}\n"
            elif article.full_text:
                text += f"    Content: {article.full_text[:300]}...\n"
            formatted.append(text)

        return "\n".join(formatted)

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from LLM response, handling common formatting issues."""
        # Try direct parsing first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Try to find JSON object in text
        json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))

        raise ValueError(f"Could not extract JSON from response: {text[:200]}")
