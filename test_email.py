#!/usr/bin/env python
"""Quick test script to verify Gmail SMTP configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

from news_forecaster.email_notifier import EmailNotifier

# Load environment variables
load_dotenv()

# Get credentials from environment
gmail_user = os.getenv("GMAIL_USER")
gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")
email_recipients = os.getenv("EMAIL_RECIPIENTS", "").split(",")

print("=" * 60)
print("EMAIL SENDING TEST")
print("=" * 60)

# Validate inputs
if not gmail_user:
    print("ERROR: GMAIL_USER not set in .env")
    exit(1)

if not gmail_app_password:
    print("ERROR: GMAIL_APP_PASSWORD not set in .env")
    exit(1)

if not email_recipients or email_recipients == [""]:
    print("ERROR: EMAIL_RECIPIENTS not set in .env")
    exit(1)

print(f"Sending from: {gmail_user}")
print(f"Sending to: {', '.join(email_recipients)}")
print()

# Create notifier and send test email
notifier = EmailNotifier(gmail_user, gmail_app_password)
success = notifier.send_test_email(email_recipients)

print()
if success:
    print("✓ Email sent successfully!")
    print("Check your inbox to verify receipt.")
else:
    print("✗ Failed to send email. Check the error message above.")
    print("Common issues:")
    print("  - GMAIL_APP_PASSWORD is incorrect or contains spaces")
    print("  - EMAIL_RECIPIENTS format is wrong (should be: user@gmail.com,other@example.com)")
    print("  - Gmail account has 2FA enabled without App Password generated")
