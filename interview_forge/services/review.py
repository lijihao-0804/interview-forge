"""Interval-repetition calculations shared by the HTTP service.

This module contains only the existing review arithmetic.  The server keeps
the public wrapper names and supplies its configured business timezone so
tests and callers retain the previous behavior and extension point.
"""

from datetime import datetime, timedelta, tzinfo


REVIEW_INTERVALS = (1, 3, 7, 15, 30, 60)
REVIEW_INTERVALS_CONTENT = (3, 7, 15, 30, 60, 90)


def review_interval(round_no: int) -> int:
    """Return the problem interval after completing ``round_no``."""
    return REVIEW_INTERVALS[min(max(round_no - 1, 0), len(REVIEW_INTERVALS) - 1)]


def due_after(completed_at: str, round_no: int, business_tz: tzinfo) -> str:
    """Calculate the next problem review date in the configured timezone."""
    completed = datetime.fromisoformat(completed_at).astimezone(business_tz).date()
    return (completed + timedelta(days=review_interval(round_no))).isoformat()


def review_interval_content(round_no: int) -> int:
    """Return the content interval after completing ``round_no``."""
    return REVIEW_INTERVALS_CONTENT[
        min(max(round_no - 1, 0), len(REVIEW_INTERVALS_CONTENT) - 1)
    ]


def due_after_content(completed_at: str, round_no: int, business_tz: tzinfo) -> str:
    """Calculate the next bookshelf-content review date."""
    completed = datetime.fromisoformat(completed_at).astimezone(business_tz).date()
    return (completed + timedelta(days=review_interval_content(round_no))).isoformat()
