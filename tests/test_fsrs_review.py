from datetime import date
import unittest

from interview_forge.services.review import (
    FSRS_RATINGS,
    fsrs_initial_state,
    fsrs_interval,
    fsrs_review,
    fsrs_retrievability,
)


class FSRSReviewTests(unittest.TestCase):
    def test_fsrs_45_four_initial_ratings_have_expected_parameters(self):
        self.assertEqual(FSRS_RATINGS, {1: "again", 2: "hard", 3: "good", 4: "easy"})
        states = [fsrs_initial_state(rating) for rating in range(1, 5)]
        self.assertEqual([state[0] for state in states], [0.4872, 1.4003, 3.7145, 13.8206])
        for actual, expected in zip(
            [state[1] for state in states], [7.6214, 6.3916, 5.1618, 3.9320]
        ):
            self.assertAlmostEqual(actual, expected)

    def test_forgetting_curve_is_ninety_percent_at_stability(self):
        self.assertAlmostEqual(fsrs_retrievability(10, 10), 0.9)
        self.assertEqual(fsrs_interval(10), 10)

    def test_review_updates_due_date_and_records_rating(self):
        result = fsrs_review(rating=4, today=date(2026, 9, 29), desired_retention=0.9)
        self.assertEqual(result["rating_name"], "easy")
        self.assertEqual(result["due_date"], "2026-10-13")
        self.assertEqual(result["scheduled_days"], 14)
        self.assertEqual(result["lapses"], 0)

    def test_again_increments_lapse_and_never_schedules_zero_days(self):
        result = fsrs_review(rating=1, today=date(2026, 9, 29), desired_retention=0.9)
        self.assertEqual(result["scheduled_days"], 1)
        self.assertEqual(result["due_date"], "2026-09-30")
        self.assertEqual(result["lapses"], 1)

    def test_existing_card_uses_elapsed_time_and_rating(self):
        base = fsrs_review(
            desired_retention=0.9,
            rating=3,
            today=date(2026, 9, 29),
            stability=10,
            difficulty=5,
            last_review_date=date(2026, 9, 19),
        )
        again = fsrs_review(
            desired_retention=0.9,
            rating=1,
            today=date(2026, 9, 29),
            stability=10,
            difficulty=5,
            last_review_date=date(2026, 9, 19),
        )
        self.assertGreater(base["stability"], 10)
        self.assertLess(again["stability"], 10)
        self.assertEqual(again["lapses"], 1)

    def test_invalid_rating_is_rejected(self):
        with self.assertRaises(ValueError):
            fsrs_review(rating=5, today=date(2026, 9, 29), desired_retention=0.9)


if __name__ == "__main__":
    unittest.main()
