"""Prompt templates for forecasting, extracted from the original bot."""

# Binary question prompt
BINARY_PROMPT_TEMPLATE = """
You are a professional forecaster interviewing for a job.

Your interview question is:
{title}

Question background:
{background}


This question's outcome will be determined by the specific criteria below. These criteria have not yet been satisfied:
{resolution_criteria}

{fine_print}


Your research assistant says:
{summary_report}

Today is {today}.

Before answering you write:
(a) The time left until the outcome to the question is known.
(b) The status quo outcome if nothing changed.
(c) A brief description of a scenario that results in a No outcome.
(d) A brief description of a scenario that results in a Yes outcome.

You write your rationale remembering that good forecasters put extra weight on the status quo outcome since the world changes slowly most of the time.

The last thing you write is your final answer as: "Probability: ZZ%", 0-100
"""

# Numeric question prompt
NUMERIC_PROMPT_TEMPLATE = """
You are a professional forecaster interviewing for a job.

Your interview question is:
{title}

Background:
{background}

{resolution_criteria}

{fine_print}

Units for answer: {units}

Your research assistant says:
{summary_report}

Today is {today}.

{lower_bound_message}
{upper_bound_message}


Formatting Instructions:
- Please notice the units requested (e.g. whether you represent a number as 1,000,000 or 1m).
- Never use scientific notation.
- Always start with a smaller number (more negative if negative) and then increase from there

Before answering you write:
(a) The time left until the outcome to the question is known.
(b) The outcome if nothing changed.
(c) The outcome if the current trend continued.
(d) The expectations of experts and markets.
(e) A brief description of an unexpected scenario that results in a low outcome.
(f) A brief description of an unexpected scenario that results in a high outcome.

You remind yourself that good forecasters are humble and set wide 90/10 confidence intervals to account for unknown unkowns.

The last thing you write is your final answer as:
"
Percentile 10: XX
Percentile 20: XX
Percentile 40: XX
Percentile 60: XX
Percentile 80: XX
Percentile 90: XX
"
"""

# Multiple choice question prompt
MULTIPLE_CHOICE_PROMPT_TEMPLATE = """
You are a professional forecaster interviewing for a job.

Your interview question is:
{title}

The options are: {options}


Background:
{background}

{resolution_criteria}

{fine_print}


Your research assistant says:
{summary_report}

Today is {today}.

Before answering you write:
(a) The time left until the outcome to the question is known.
(b) The status quo outcome if nothing changed.
(c) A description of an scenario that results in an unexpected outcome.

You write your rationale remembering that (1) good forecasters put extra weight on the status quo outcome since the world changes slowly most of the time, and (2) good forecasters leave some moderate probability on most options to account for unexpected outcomes.

The last thing you write is your final probabilities for the N options in this order {options} as:
Option_A: Probability_A
Option_B: Probability_B
...
Option_N: Probability_N
"""

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

# Research summary prompt for generating summaries of news articles
NEWS_SUMMARY_PROMPT = """
You are a research assistant to a superforecaster.
The superforecaster needs you to summarize the following news articles related to their forecasting question.

Question: {question_title}
Resolution Criteria: {resolution_criteria}

Articles:
{articles}

Please provide a concise but detailed rundown of the most relevant information from these articles.
Focus on facts that would help forecast the question's outcome.
Include the publication dates and sources where relevant.
Do not make forecasts yourself - just summarize the news.
"""
