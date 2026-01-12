"""Email notifications via Gmail SMTP."""

from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .models import NewsUpdate


# HTML email template for news alerts
EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        .header {{ background: #1a73e8; color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: white; padding: 20px; border-radius: 0 0 8px 8px; }}
        .question {{ background: #f8f9fa; padding: 15px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #dc3545; }}
        .change-summary {{ background: #fff3cd; padding: 15px; border-radius: 4px; margin: 10px 0; border: 1px solid #ffc107; }}
        .significance {{ font-weight: bold; color: #dc3545; }}
        .new-articles {{ margin-top: 15px; }}
        .new-articles h4 {{ margin-bottom: 10px; color: #333; }}
        .article {{ padding: 10px; border-bottom: 1px solid #eee; }}
        .article:last-child {{ border-bottom: none; }}
        .article-title {{ font-weight: bold; color: #1a73e8; }}
        .article-meta {{ color: #666; font-size: 12px; margin-top: 5px; }}
        footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
        a {{ color: #1a73e8; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>News Alert</h1>
        <p>Generated: {timestamp}</p>
        <p>{summary}</p>
    </div>
    <div class="content">
        {questions_html}
    </div>
    <footer>
        <p>This is an automated news alert for Metaculus questions. Source: <a href="https://www.metaculus.com">Metaculus</a>.</p>
        <p>To unsubscribe, update your EMAIL_RECIPIENTS environment variable.</p>
    </footer>
</body>
</html>
"""

QUESTION_TEMPLATE = """
<div class="question">
    <h2><a href="{page_url}">{title}</a></h2>
    <p class="significance">Significance Score: {score:.0%}</p>
    <div class="change-summary">
        <strong>What Changed:</strong>
        <p>{change_summary}</p>
    </div>
    <div class="new-articles">
        <h4>New Articles ({new_article_count})</h4>
        {articles_html}
    </div>
</div>
"""


class EmailNotifier:
    """Sends email notifications via Gmail SMTP."""

    def __init__(self, gmail_user: str, gmail_app_password: str):
        self.gmail_user = gmail_user
        self.gmail_app_password = gmail_app_password
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 465

    def send_news_alert(
        self,
        recipients: list[str],
        updates: list[NewsUpdate],
        subject: Optional[str] = None,
    ) -> bool:
        """
        Send an email alerting about significant news changes.

        Args:
            recipients: List of email addresses
            updates: List of NewsUpdate objects with significant changes
            subject: Optional custom subject line

        Returns:
            True if email was sent successfully
        """
        if not recipients:
            print("No recipients specified, skipping email.")
            return False

        if not updates:
            print("No updates to send, skipping email.")
            return False

        # Generate subject
        if subject is None:
            subject = f"News Alert: {len(updates)} question(s) with significant changes"

        # Generate HTML content
        questions_html = ""
        for update in updates:
            questions_html += self._render_update(update)

        summary = f"{len(updates)} question(s) have significant news changes that may affect forecasts"

        html_content = EMAIL_TEMPLATE.format(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            summary=summary,
            questions_html=questions_html,
        )

        # Create email message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.gmail_user
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html_content, "html"))

        # Send email
        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.gmail_user, self.gmail_app_password)
                server.sendmail(self.gmail_user, recipients, msg.as_string())
            print(f"Email sent to {len(recipients)} recipient(s)")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    def _render_update(self, update: NewsUpdate) -> str:
        """Render a single news update as HTML."""
        if not update.change_report:
            return ""

        # New articles HTML
        articles_html = ""
        for article in update.change_report.new_articles[:10]:
            pub_date = (
                article.published_date.strftime("%Y-%m-%d")
                if article.published_date
                else "Unknown date"
            )
            summary_text = ""
            if article.summary:
                summary_text = f"<p>{article.summary[:300]}{'...' if len(article.summary) > 300 else ''}</p>"

            articles_html += f"""
            <div class="article">
                <div class="article-title"><a href="{article.url}">{article.title}</a></div>
                <div class="article-meta">{article.source} | {pub_date}</div>
                {summary_text}
            </div>
            """

        return QUESTION_TEMPLATE.format(
            page_url=update.question.page_url,
            title=update.question.title,
            score=update.change_report.significance_score,
            change_summary=update.change_report.change_summary,
            new_article_count=len(update.change_report.new_articles),
            articles_html=articles_html if articles_html else "<p>No new articles identified.</p>",
        )

    def send_test_email(self, recipients: list[str]) -> bool:
        """Send a test email to verify configuration."""
        html_content = """
        <html>
        <body>
            <h1>Test Email from News Aggregator</h1>
            <p>If you received this email, your Gmail SMTP configuration is working correctly.</p>
            <p>Sent at: {timestamp}</p>
        </body>
        </html>
        """.format(timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "News Aggregator - Test Email"
        msg["From"] = self.gmail_user
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.gmail_user, self.gmail_app_password)
                server.sendmail(self.gmail_user, recipients, msg.as_string())
            print("Test email sent successfully!")
            return True
        except Exception as e:
            print(f"Failed to send test email: {e}")
            return False
