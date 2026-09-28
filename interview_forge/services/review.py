"""Legacy review intervals and FSRS-4.5 scheduling arithmetic.

The legacy wrappers remain available to preserve existing callers and their
business-timezone behavior; newly rated reviews use the explicit FSRS model.
"""

import math
from datetime import date, datetime, timedelta, tzinfo


REVIEW_INTERVALS = (1, 3, 7, 15, 30, 60)
REVIEW_INTERVALS_CONTENT = (3, 7, 15, 30, 60, 90)
FSRS_VERSION = "4.5"
FSRS_DESIRED_RETENTION = 0.9
FSRS_MAX_INTERVAL_DAYS = 365
FSRS_WEIGHTS = (
    0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975,
    0.031, 1.6474, 0.1367, 1.0461, 2.1072, 0.0793, 0.3246,
    1.587, 0.2272, 2.8755,
)
FSRS_RATINGS = {1: "again", 2: "hard", 3: "good", 4: "easy"}


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


def fsrs_retrievability(elapsed_days: int | float, stability: float) -> float:
    """FSRS-4.5 forgetting curve; stability is the interval at 90% recall."""
    safe_stability = max(float(stability), 0.001)
    return (1.0 + (19.0 / 81.0) * max(float(elapsed_days), 0.0) / safe_stability) ** -0.5


def fsrs_interval(stability: float, desired_retention: float = FSRS_DESIRED_RETENTION) -> int:
    """Convert stability to a whole-day interval for the requested retention."""
    retention = min(max(float(desired_retention), 0.70), 0.99)
    factor = (81.0 / 19.0) * (retention ** -2.0 - 1.0)
    days = max(1, round(max(float(stability), 0.001) * factor))
    return min(days, FSRS_MAX_INTERVAL_DAYS)


def fsrs_initial_state(rating: int) -> tuple[float, float]:
    """Return FSRS-4.5 initial stability and difficulty for a first review."""
    _validate_rating(rating)
    stability = FSRS_WEIGHTS[rating - 1]
    difficulty = FSRS_WEIGHTS[4] - (rating - 3) * FSRS_WEIGHTS[5]
    return max(stability, 0.1), min(max(difficulty, 1.0), 10.0)


def _validate_rating(rating: int) -> int:
    if isinstance(rating, bool):
        raise ValueError("rating must be an integer from 1 to 4")
    if isinstance(rating, float) and not rating.is_integer():
        raise ValueError("rating must be an integer from 1 to 4")
    try:
        value = int(rating)
    except (TypeError, ValueError) as exc:
        raise ValueError("rating must be an integer from 1 to 4") from exc
    if value not in FSRS_RATINGS:
        raise ValueError("rating must be an integer from 1 to 4")
    return value


def fsrs_review(
    *,
    rating: int,
    today: date,
    stability: float | None = None,
    difficulty: float | None = None,
    last_review_date: date | None = None,
    lapses: int = 0,
    desired_retention: float = FSRS_DESIRED_RETENTION,
) -> dict[str, float | int | str]:
    """Apply one FSRS-4.5 rating and return the updated memory state."""
    grade = _validate_rating(rating)
    if stability is None or difficulty is None or last_review_date is None:
        next_stability, next_difficulty = fsrs_initial_state(grade)
        next_lapses = int(lapses) + (1 if grade == 1 else 0)
    else:
        old_stability = max(float(stability), 0.001)
        old_difficulty = min(max(float(difficulty), 1.0), 10.0)
        elapsed = max((today - last_review_date).days, 0)
        retrievability = fsrs_retrievability(elapsed, old_stability)
        w = FSRS_WEIGHTS
        initial_good_difficulty = w[4]
        next_difficulty = (
            w[7] * initial_good_difficulty
            + (1.0 - w[7]) * (old_difficulty - w[6] * (grade - 3))
        )
        next_difficulty = min(max(next_difficulty, 1.0), 10.0)
        if grade == 1:
            next_stability = (
                w[11]
                * old_difficulty ** (-w[12])
                * ((old_stability + 1.0) ** w[13] - 1.0)
                * math.exp(w[14] * (1.0 - retrievability))
            )
            next_lapses = int(lapses) + 1
        else:
            multiplier = 1.0
            if grade == 2:
                multiplier *= w[15]
            elif grade == 4:
                multiplier *= w[16]
            increase = (
                math.exp(w[8])
                * (11.0 - old_difficulty)
                * old_stability ** (-w[9])
                * (math.exp(w[10] * (1.0 - retrievability)) - 1.0)
                * multiplier
            )
            next_stability = old_stability * (1.0 + max(increase, 0.0))
            next_lapses = int(lapses)

    next_stability = min(max(float(next_stability), 0.1), 36500.0)
    interval = fsrs_interval(next_stability, desired_retention)
    return {
        "stability": next_stability,
        "difficulty": next_difficulty,
        "scheduled_days": interval,
        "due_date": (today + timedelta(days=interval)).isoformat(),
        "lapses": next_lapses,
        "rating": grade,
        "rating_name": FSRS_RATINGS[grade],
    }
