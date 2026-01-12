"""News aggregation using Exa AI with optional Firecrawl fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .models import NewsArticle, NewsSnapshot, QuestionMetadata


class NewsAggregator:
    """Aggregates news articles related to forecasting questions using Exa AI."""

    def __init__(
        self,
        exa_api_key: str,
        firecrawl_api_key: Optional[str] = None,
        min_content_length: int = 500,
    ):
        self.exa_api_key = exa_api_key
        self.firecrawl_api_key = firecrawl_api_key
        self.min_content_length = min_content_length

        # Lazy imports to avoid requiring packages if not used
        self._exa = None
        self._firecrawl = None

    @property
    def exa(self):
        """Lazy load Exa client."""
        if self._exa is None:
            from exa_py import Exa
            self._exa = Exa(api_key=self.exa_api_key)
        return self._exa

    @property
    def firecrawl(self):
        """Lazy load Firecrawl client."""
        if self._firecrawl is None and self.firecrawl_api_key:
            from firecrawl import FirecrawlApp
            self._firecrawl = FirecrawlApp(api_key=self.firecrawl_api_key)
        return self._firecrawl

    def fetch_news_for_question(
        self,
        question: QuestionMetadata,
        since_date: Optional[datetime] = None,
        num_results: int = 15,
    ) -> NewsSnapshot:
        """
        Fetch news articles related to a question using Exa AI.

        Args:
            question: The question to find related news for
            since_date: Only fetch articles published after this date
            num_results: Maximum number of results to fetch

        Returns:
            NewsSnapshot containing the fetched articles
        """
        search_query = self._build_search_query(question)

        # Build Exa search parameters
        search_kwargs = {
            "num_results": num_results,
            "text": {"max_characters": 10000},
            "use_autoprompt": True,
        }

        if since_date:
            search_kwargs["start_published_date"] = since_date.strftime("%Y-%m-%d")

        # Perform search with content extraction
        results = self.exa.search_and_contents(search_query, **search_kwargs)

        # Parse results into NewsArticle objects
        articles = []
        for result in results.results:
            article = self._parse_exa_result(result)

            # Optionally use Firecrawl for thin content
            if (
                self.firecrawl
                and article.full_text
                and len(article.full_text) < self.min_content_length
            ):
                article = self._enhance_with_firecrawl(article)

            articles.append(article)

        return NewsSnapshot(
            question_id=question.question_id,
            fetched_at=datetime.now(timezone.utc),
            articles=articles,
            search_query=search_query,
        )

    def _build_search_query(self, question: QuestionMetadata) -> str:
        """Build a semantic search query from question content."""
        # Use title as primary query, with resolution criteria for context
        query_parts = [question.title]

        # Add key resolution criteria if present (truncated)
        if question.resolution_criteria:
            criteria_snippet = question.resolution_criteria[:200]
            query_parts.append(criteria_snippet)

        return ". ".join(query_parts)

    def _parse_exa_result(self, result) -> NewsArticle:
        """Parse an Exa search result into a NewsArticle."""
        # Parse published date
        published_date = None
        if hasattr(result, "published_date") and result.published_date:
            try:
                published_date = datetime.fromisoformat(
                    result.published_date.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Extract source from URL
        source = ""
        if result.url:
            from urllib.parse import urlparse
            parsed = urlparse(result.url)
            source = parsed.netloc.replace("www.", "")

        # Safely extract highlights (could be None even if attribute exists)
        highlights = getattr(result, "highlights", None)
        summary = highlights[0] if highlights else ""

        return NewsArticle(
            url=result.url or "",
            title=result.title or "",
            summary=summary,
            full_text=getattr(result, "text", None),
            published_date=published_date,
            source=source,
            relevance_score=getattr(result, "score", None),
        )

    def _enhance_with_firecrawl(self, article: NewsArticle) -> NewsArticle:
        """Use Firecrawl to get full content for an article with thin content."""
        if not self.firecrawl or not article.url:
            return article

        try:
            result = self.firecrawl.scrape_url(article.url, params={"formats": ["markdown"]})
            if result and result.get("markdown"):
                article.full_text = result["markdown"]
        except Exception as e:
            print(f"Firecrawl enhancement failed for {article.url}: {e}")

        return article

    def merge_with_previous(
        self,
        new_snapshot: NewsSnapshot,
        previous_snapshot: Optional[NewsSnapshot],
        max_articles: int = 50,
    ) -> NewsSnapshot:
        """
        Merge new articles with previous snapshot, deduplicating by URL.

        Args:
            new_snapshot: Newly fetched news snapshot
            previous_snapshot: Previous news snapshot (if any)
            max_articles: Maximum total articles to keep

        Returns:
            Merged NewsSnapshot with deduplicated articles
        """
        if not previous_snapshot:
            return new_snapshot

        # Get existing URLs for deduplication
        existing_urls = {a.url for a in previous_snapshot.articles}

        # Filter to genuinely new articles
        new_articles = [a for a in new_snapshot.articles if a.url not in existing_urls]

        # Combine: new articles first, then previous
        combined = new_articles + previous_snapshot.articles

        # Limit total articles
        combined = combined[:max_articles]

        return NewsSnapshot(
            question_id=new_snapshot.question_id,
            fetched_at=new_snapshot.fetched_at,
            articles=combined,
            search_query=new_snapshot.search_query,
        )

    def get_new_articles(
        self,
        current_snapshot: NewsSnapshot,
        previous_snapshot: Optional[NewsSnapshot],
    ) -> list[NewsArticle]:
        """Get articles that are in current but not in previous snapshot."""
        if not previous_snapshot:
            return current_snapshot.articles

        previous_urls = {a.url for a in previous_snapshot.articles}
        return [a for a in current_snapshot.articles if a.url not in previous_urls]
