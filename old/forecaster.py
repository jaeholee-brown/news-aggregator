"""LLM-based forecasting for Metaculus questions."""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, model_validator

from .models import Forecast, NewsSnapshot, QuestionMetadata
from .prompts import (
    BINARY_PROMPT_TEMPLATE,
    MULTIPLE_CHOICE_PROMPT_TEMPLATE,
    NEWS_SUMMARY_PROMPT,
    NUMERIC_PROMPT_TEMPLATE,
)


class Forecaster:
    """Generates forecasts using LLM based on question and news context."""

    def __init__(
        self,
        openai_api_key: str,
        model: str = "gpt-5.2",
        num_runs: int = 5,
        temperature: float = 0.3,
    ):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.num_runs = num_runs
        self.temperature = temperature
        self._semaphore = asyncio.Semaphore(5)  # Limit concurrent requests

    async def generate_forecast(
        self,
        question: QuestionMetadata,
        news_snapshot: NewsSnapshot,
    ) -> Forecast:
        """Generate a forecast for a question based on news context."""
        # First, summarize the news for the prompt
        news_summary = await self._summarize_news(question, news_snapshot)

        # Generate forecast based on question type
        if question.question_type == "binary":
            forecast_value, reasoning = await self._forecast_binary(question, news_summary)
        elif question.question_type == "multiple_choice":
            forecast_value, reasoning = await self._forecast_multiple_choice(
                question, news_summary
            )
        elif question.question_type in ("numeric", "discrete"):
            forecast_value, reasoning = await self._forecast_numeric(question, news_summary)
        else:
            raise ValueError(f"Unknown question type: {question.question_type}")

        return Forecast(
            question_id=question.question_id,
            question_type=question.question_type,
            forecast_value=forecast_value,
            reasoning=reasoning,
            generated_at=datetime.now(timezone.utc),
            model_used=self.model,
            news_snapshot_id=news_snapshot.snapshot_id,
        )

    async def _call_llm(self, prompt: str) -> str:
        """Make a completion request to OpenAI with rate limiting."""
        async with self._semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )
            answer = response.choices[0].message.content
            if answer is None:
                raise ValueError("No answer returned from LLM")
            return answer

    async def _summarize_news(
        self, question: QuestionMetadata, news_snapshot: NewsSnapshot
    ) -> str:
        """Summarize news articles for the forecast prompt."""
        if not news_snapshot.articles:
            return "No recent news articles found."

        # Format articles for the summary prompt
        articles_text = ""
        for i, article in enumerate(news_snapshot.articles[:10], 1):
            pub_date = (
                article.published_date.strftime("%Y-%m-%d")
                if article.published_date
                else "Unknown date"
            )
            articles_text += f"\n[Article {i}]\n"
            articles_text += f"Title: {article.title}\n"
            articles_text += f"Source: {article.source}\n"
            articles_text += f"Date: {pub_date}\n"
            if article.summary:
                articles_text += f"Summary: {article.summary}\n"
            if article.full_text:
                # Truncate long text
                text = article.full_text[:2000]
                articles_text += f"Content: {text}...\n" if len(article.full_text) > 2000 else f"Content: {text}\n"

        prompt = NEWS_SUMMARY_PROMPT.format(
            question_title=question.title,
            resolution_criteria=question.resolution_criteria or "",
            articles=articles_text,
        )

        return await self._call_llm(prompt)

    async def _forecast_binary(
        self, question: QuestionMetadata, news_summary: str
    ) -> tuple[float, str]:
        """Generate forecast for a binary question."""
        today = datetime.now().strftime("%Y-%m-%d")

        prompt = BINARY_PROMPT_TEMPLATE.format(
            title=question.title,
            today=today,
            background=question.background_info or "",
            resolution_criteria=question.resolution_criteria or "",
            fine_print=question.fine_print or "",
            summary_report=news_summary,
        )

        # Run multiple times and take median
        async def get_single_forecast():
            rationale = await self._call_llm(prompt)
            prob = extract_probability_from_response(rationale)
            return prob, rationale

        results = await asyncio.gather(*[get_single_forecast() for _ in range(self.num_runs)])
        probabilities = [r[0] for r in results]
        rationales = [r[1] for r in results]

        median_prob = float(np.median(probabilities)) / 100  # Convert to decimal
        combined_reasoning = f"Median probability: {median_prob:.2%}\n\n"
        combined_reasoning += "\n\n---\n\n".join(
            f"Run {i+1} ({p}%):\n{r}" for i, (p, r) in enumerate(zip(probabilities, rationales))
        )

        return median_prob, combined_reasoning

    async def _forecast_multiple_choice(
        self, question: QuestionMetadata, news_summary: str
    ) -> tuple[dict[str, float], str]:
        """Generate forecast for a multiple choice question."""
        today = datetime.now().strftime("%Y-%m-%d")
        options = question.options or []

        prompt = MULTIPLE_CHOICE_PROMPT_TEMPLATE.format(
            title=question.title,
            today=today,
            options=options,
            background=question.background_info or "",
            resolution_criteria=question.resolution_criteria or "",
            fine_print=question.fine_print or "",
            summary_report=news_summary,
        )

        async def get_single_forecast():
            rationale = await self._call_llm(prompt)
            probs = extract_option_probabilities_from_response(rationale, options)
            return probs, rationale

        results = await asyncio.gather(*[get_single_forecast() for _ in range(self.num_runs)])
        all_probs = [r[0] for r in results]
        rationales = [r[1] for r in results]

        # Average probabilities across runs
        avg_probs: dict[str, float] = {}
        for option in options:
            option_probs = [p.get(option, 0) for p in all_probs]
            avg_probs[option] = sum(option_probs) / len(option_probs)

        # Normalize to sum to 1
        total = sum(avg_probs.values())
        if total > 0:
            avg_probs = {k: v / total for k, v in avg_probs.items()}

        combined_reasoning = f"Average probabilities: {avg_probs}\n\n"
        combined_reasoning += "\n\n---\n\n".join(
            f"Run {i+1}:\n{r}" for i, r in enumerate(rationales)
        )

        return avg_probs, combined_reasoning

    async def _forecast_numeric(
        self, question: QuestionMetadata, news_summary: str
    ) -> tuple[list[float], str]:
        """Generate forecast for a numeric/discrete question."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Build bound messages
        upper_bound_message = ""
        lower_bound_message = ""
        if question.open_upper_bound is False and question.upper_bound is not None:
            upper_bound_message = f"The outcome can not be higher than {question.upper_bound}."
        if question.open_lower_bound is False and question.lower_bound is not None:
            lower_bound_message = f"The outcome can not be lower than {question.lower_bound}."

        prompt = NUMERIC_PROMPT_TEMPLATE.format(
            title=question.title,
            today=today,
            background=question.background_info or "",
            resolution_criteria=question.resolution_criteria or "",
            fine_print=question.fine_print or "",
            summary_report=news_summary,
            lower_bound_message=lower_bound_message,
            upper_bound_message=upper_bound_message,
            units=question.unit_of_measure or "Not stated",
        )

        async def get_single_forecast():
            rationale = await self._call_llm(prompt)
            percentiles = extract_percentiles_from_response(rationale)
            cdf = generate_continuous_cdf(
                percentiles,
                question.question_type,
                question.open_upper_bound or True,
                question.open_lower_bound or True,
                question.upper_bound or 100,
                question.lower_bound or 0,
                question.zero_point,
                201 if question.question_type == "numeric" else 51,  # Discrete uses fewer points
            )
            return cdf, rationale

        results = await asyncio.gather(*[get_single_forecast() for _ in range(self.num_runs)])
        all_cdfs = [r[0] for r in results]
        rationales = [r[1] for r in results]

        # Median CDF
        median_cdf = np.median(np.array(all_cdfs), axis=0).tolist()

        combined_reasoning = f"Median CDF (first 10 values): {median_cdf[:10]}...\n\n"
        combined_reasoning += "\n\n---\n\n".join(
            f"Run {i+1}:\n{r}" for i, r in enumerate(rationales)
        )

        return median_cdf, combined_reasoning


# ==================== Extraction Functions ====================
# Ported from main_with_no_framework.py


def extract_probability_from_response(forecast_text: str) -> float:
    """Extract probability percentage from LLM response."""
    matches = re.findall(r"(\d+)%", forecast_text)
    if matches:
        number = int(matches[-1])
        number = min(99, max(1, number))  # Clamp between 1 and 99
        return number
    raise ValueError(f"Could not extract prediction from response: {forecast_text[:200]}")


def extract_percentiles_from_response(forecast_text: str) -> dict:
    """Extract percentile values from LLM response."""
    pattern = r"^.*(?:P|p)ercentile.*$"
    number_pattern = (
        r"-\s*(?:[^\d\-]*\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)|(\d+(?:,\d{3})*(?:\.\d+)?)"
    )
    results = []

    for line in forecast_text.split("\n"):
        if re.match(pattern, line):
            numbers = re.findall(number_pattern, line)
            numbers_no_commas = [
                next(num for num in match if num).replace(",", "") for match in numbers
            ]
            numbers_parsed = [
                float(num) if "." in num else int(num) for num in numbers_no_commas
            ]
            if len(numbers_parsed) > 1:
                first_number = numbers_parsed[0]
                last_number = numbers_parsed[-1]
                if "-" in line.split(":")[-1]:
                    last_number = -abs(last_number)
                results.append((first_number, last_number))

    percentile_values = {}
    for first_num, second_num in results:
        percentile_values[first_num] = second_num

    if len(percentile_values) > 0:
        return percentile_values
    raise ValueError(f"Could not extract percentiles from response: {forecast_text[:200]}")


def extract_option_probabilities_from_response(
    forecast_text: str, options: list[str]
) -> dict[str, float]:
    """Extract option probabilities from LLM response."""
    number_pattern = r"-?\d+(?:,\d{3})*(?:\.\d+)?"
    results = []

    for line in forecast_text.split("\n"):
        numbers = re.findall(number_pattern, line)
        numbers_no_commas = [num.replace(",", "") for num in numbers]
        numbers_parsed = [
            float(num) if "." in num else int(num) for num in numbers_no_commas
        ]
        if len(numbers_parsed) >= 1:
            results.append(numbers_parsed[-1])

    num_options = len(options)
    if len(results) >= num_options:
        probs = results[-num_options:]
        # Normalize
        total = sum(probs)
        if total > 0:
            probs = [p / total for p in probs]
        return dict(zip(options, probs))

    raise ValueError(f"Could not extract option probabilities: {forecast_text[:200]}")


# ==================== Numeric Distribution ====================


class Percentile(BaseModel):
    """A percentile-value pair for numeric distributions."""

    percentile: float = Field(description="A number between 0 and 1")
    value: float = Field(description="The value at this percentile")

    @model_validator(mode="after")
    def validate_percentile(self) -> "Percentile":
        if self.percentile < 0 or self.percentile > 1:
            raise ValueError(f"Percentile must be between 0 and 1, got {self.percentile}")
        return self


def generate_continuous_cdf(
    percentile_values: dict,
    question_type: str,
    open_upper_bound: bool,
    open_lower_bound: bool,
    upper_bound: float,
    lower_bound: float,
    zero_point: Optional[float],
    cdf_size: int,
) -> list[float]:
    """Generate a continuous CDF from percentile values."""
    # Convert dict to list of Percentile objects
    percentiles = [
        Percentile(percentile=p / 100, value=v) for p, v in percentile_values.items()
    ]

    # Sort by percentile
    percentiles.sort(key=lambda x: x.percentile)

    # Simple linear interpolation to generate CDF
    cdf = []
    cdf_locations = [i / (cdf_size - 1) for i in range(cdf_size)]

    # Add boundary percentiles
    percentile_dict = {p.percentile: p.value for p in percentiles}

    # Ensure we have 0 and 1 bounds
    if 0 not in percentile_dict:
        percentile_dict[0] = lower_bound
    if 1 not in percentile_dict:
        percentile_dict[1] = upper_bound

    sorted_percentiles = sorted(percentile_dict.items())

    for loc in cdf_locations:
        # Find surrounding percentiles
        lower_p, lower_v = sorted_percentiles[0]
        upper_p, upper_v = sorted_percentiles[-1]

        for i, (p, v) in enumerate(sorted_percentiles[:-1]):
            next_p, next_v = sorted_percentiles[i + 1]
            if p <= loc <= next_p:
                lower_p, lower_v = p, v
                upper_p, upper_v = next_p, next_v
                break

        # Linear interpolation
        if upper_p == lower_p:
            cdf_value = lower_p
        else:
            cdf_value = lower_p + (upper_p - lower_p) * (loc - lower_p) / (upper_p - lower_p)

        cdf.append(max(0, min(1, cdf_value)))

    # Ensure monotonically increasing
    for i in range(1, len(cdf)):
        if cdf[i] < cdf[i - 1]:
            cdf[i] = cdf[i - 1] + 0.0001

    return cdf
