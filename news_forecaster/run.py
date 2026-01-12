"""Main orchestration script for the news aggregator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from .change_detector import ChangeDetector
from .config import Config
from .email_notifier import EmailNotifier
from .metaculus_client import MetaculusClient
from .models import ChangeReport, NewsUpdate, QuestionMetadata
from .news_aggregator import NewsAggregator
from .storage import Storage


async def process_question(
    question: QuestionMetadata,
    news_agg: NewsAggregator,
    change_detector: ChangeDetector,
    storage: Storage,
) -> Optional[NewsUpdate]:
    """
    Process a single question: fetch news and detect changes.

    Returns:
        NewsUpdate if processing was successful, None otherwise
    """
    print(f"\n{'='*60}")
    print(f"Processing: {question.title}")
    print(f"URL: {question.page_url}")
    print(f"Type: {question.question_type}")

    try:
        # Load previous state
        previous_news = storage.load_latest_news(question.question_id)

        # Determine time window for new news
        since_date = None
        if previous_news:
            # Overlap by 1 hour for safety
            since_date = previous_news.fetched_at - timedelta(hours=1)
            print(f"Fetching news since: {since_date}")

        # Fetch new news
        print("Fetching news via Exa AI...")
        new_news = news_agg.fetch_news_for_question(question, since_date)
        print(f"Found {len(new_news.articles)} articles")

        # Merge with previous news
        merged_news = news_agg.merge_with_previous(new_news, previous_news)
        print(f"Total articles after merge: {len(merged_news.articles)}")

        # Detect changes
        change_report: Optional[ChangeReport] = None
        if previous_news:
            print("Detecting news changes...")
            change_report = await change_detector.detect_changes(
                question, previous_news, merged_news
            )
            print(f"  -> Significance score: {change_report.significance_score:.2f}")
            print(f"  -> Is significant: {change_report.is_significant}")
            if change_report.change_summary:
                print(f"  -> Summary: {change_report.change_summary[:200]}")
        else:
            # First run - if we found articles, mark as significant so user gets notified
            print("First run - no previous news to compare")
            if merged_news.articles:
                print(f"  -> Found {len(merged_news.articles)} articles on first run - marking as SIGNIFICANT")
                change_report = ChangeReport(
                    question_id=question.question_id,
                    detected_at=datetime.now(timezone.utc),
                    previous_snapshot_id=None,
                    current_snapshot_id=merged_news.snapshot_id,
                    change_summary=f"First news aggregation: found {len(merged_news.articles)} relevant article(s).",
                    significance_score=1.0,  # First run is always significant
                    is_significant=True,
                    new_articles=merged_news.articles,
                )

        # Save news snapshot
        storage.save_news(question.question_id, merged_news)

        # Save question metadata
        storage.save_question(question)

        return NewsUpdate(
            question=question,
            news_snapshot=merged_news,
            change_report=change_report,
        )

    except Exception as e:
        print(f"Error processing question {question.question_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def get_questions_to_process(
    client: MetaculusClient,
    config: Config,
    storage: Storage,
) -> list[QuestionMetadata]:
    """Fetch questions from specified IDs and series."""
    questions = []

    # Individual questions
    for qid in config.question_ids:
        print(f"Fetching question {qid}...")
        q = client.get_question(qid)
        if q:
            questions.append(q)
            print(f"  Found: {q.title}")

    # Questions from series
    for series_id in config.series_ids:
        print(f"Fetching questions from series {series_id}...")
        series_questions = client.get_questions_in_series(series_id)
        print(f"  Found {len(series_questions)} questions")
        questions.extend(series_questions)

        # Save series mapping
        storage.save_series(series_id, [q.question_id for q in series_questions])

    # Deduplicate by question_id
    seen = set()
    unique_questions = []
    for q in questions:
        if q.question_id not in seen:
            seen.add(q.question_id)
            unique_questions.append(q)

    return unique_questions


async def main():
    """Main entry point for the news aggregator."""
    print("=" * 60)
    print("NEWS AGGREGATOR")
    print(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # Load configuration
    config = Config.from_env()

    # Validate configuration
    missing = config.validate()
    if missing:
        print(f"ERROR: Missing required configuration: {', '.join(missing)}")
        print("Please set the required environment variables and try again.")
        return

    # Initialize components
    print("\nInitializing components...")
    print(f"  Significance threshold: {config.significance_threshold}")
    print(f"  Change detection model: {config.change_detection_model}")
    metaculus = MetaculusClient(config.metaculus_token)
    news_agg = NewsAggregator(
        config.exa_api_key,
        config.firecrawl_api_key,
        config.min_content_length,
    )
    change_detector = ChangeDetector(
        config.openai_api_key,
        model=config.change_detection_model,
        significance_threshold=config.significance_threshold,
    )
    email_notifier = (
        EmailNotifier(config.gmail_user, config.gmail_app_password)
        if config.gmail_user and config.gmail_app_password
        else None
    )
    storage = Storage(config.data_dir)

    # Fetch questions to process
    print("\nFetching questions...")
    questions = await get_questions_to_process(metaculus, config, storage)
    print(f"Total questions to process: {len(questions)}")

    if not questions:
        print("No questions to process. Check your QUESTION_IDS and SERIES_IDS.")
        return

    # Process each question
    updates: list[NewsUpdate] = []
    for question in questions:
        update = await process_question(
            question,
            news_agg,
            change_detector,
            storage,
        )
        if update:
            updates.append(update)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Questions processed: {len(updates)}/{len(questions)}")

    significant_updates = [
        u for u in updates if u.change_report and u.change_report.is_significant
    ]
    print(f"Significant news changes: {len(significant_updates)}")

    print("\nAll scores:")
    for update in updates:
        score = update.change_report.significance_score if update.change_report else 0.0
        is_sig = update.change_report.is_significant if update.change_report else False
        if update.change_report:
            if is_sig:
                marker = "***"  # Significant
            else:
                marker = "   "
            print(f"  {marker} score={score:.2f} | {update.question.title[:60]}")
        else:
            print(f"       [NO CHANGE REPORT] | {update.question.title[:60]}")

    # Send email notification if there are significant updates
    if email_notifier and config.email_recipients:
        if significant_updates:
            print(f"\nSending email to {len(config.email_recipients)} recipient(s)...")
            email_notifier.send_news_alert(config.email_recipients, significant_updates)
        else:
            print("\nNo significant changes to email about.")
    elif not email_notifier:
        print("\nEmail not configured (GMAIL_USER/GMAIL_APP_PASSWORD not set).")
    elif not config.email_recipients:
        print("\nNo email recipients configured.")

    print("\n" + "=" * 60)
    print(f"Completed at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
