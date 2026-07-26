from __future__ import annotations

import unittest

import numpy as np

from workout_generator.preworkout import (
    assignment_for_preworkout_roll,
    generate_daily_assignments,
    record_completion,
    record_failure,
    record_miss,
    replace_unsaved_for_date,
)


class PreWorkoutTests(unittest.TestCase):
    def test_generate_daily_assignments_returns_two_known_values(self) -> None:
        assignments = generate_daily_assignments(np.random.RandomState(0))

        self.assertEqual(len(assignments), 2)
        self.assertTrue(all(assignment in {"push ups", "sit ups", "squats", "break"} for assignment in assignments))

    def test_preworkout_roll_thresholds_match_requested_distribution(self) -> None:
        self.assertEqual(assignment_for_preworkout_roll(0.0), "push ups")
        self.assertEqual(assignment_for_preworkout_roll(0.249999), "push ups")
        self.assertEqual(assignment_for_preworkout_roll(0.25), "sit ups")
        self.assertEqual(assignment_for_preworkout_roll(0.374999), "sit ups")
        self.assertEqual(assignment_for_preworkout_roll(0.375), "squats")
        self.assertEqual(assignment_for_preworkout_roll(0.499999), "squats")
        self.assertEqual(assignment_for_preworkout_roll(0.5), "break")
        self.assertEqual(assignment_for_preworkout_roll(1.0), "break")

    def test_generate_daily_assignments_uses_one_continuous_roll_per_slot(self) -> None:
        assignments = generate_daily_assignments(_FixedUnitRandom([0.249999, 0.25]))

        self.assertEqual(assignments, ["push ups", "sit ups"])

    def test_record_completion_needs_two_matching_results_to_adjust_number(self) -> None:
        state = {
            "push ups": {"num": 10, "str": 0},
            "unsaved": [],
        }

        record_completion(state, "push ups")
        self.assertEqual(state["push ups"], {"num": 10, "str": 1})

        record_completion(state, "push ups")
        self.assertEqual(state["push ups"], {"num": 11, "str": 0})

    def test_record_failure_needs_two_matching_results_to_lower_number(self) -> None:
        state = {
            "push ups": {"num": 10, "str": 0},
            "unsaved": [],
        }

        record_failure(state, "push ups")
        self.assertEqual(state["push ups"], {"num": 10, "str": -1})

        record_failure(state, "push ups")
        self.assertEqual(state["push ups"], {"num": 9, "str": 0})

    def test_record_completion_after_failure_flips_streak_to_one(self) -> None:
        state = {
            "push ups": {"num": 10, "str": -1},
            "unsaved": [],
        }

        record_completion(state, "push ups")

        self.assertEqual(state["push ups"], {"num": 10, "str": 1})

    def test_record_failure_after_completion_flips_streak_to_negative_one(self) -> None:
        state = {
            "push ups": {"num": 10, "str": 1},
            "unsaved": [],
        }

        record_failure(state, "push ups")

        self.assertEqual(state["push ups"], {"num": 10, "str": -1})

    def test_record_failure_holds_streak_at_minimum_target(self) -> None:
        state = {
            "squats": {"num": 1, "str": -1},
            "unsaved": [],
        }

        record_failure(state, "squats")

        self.assertEqual(state["squats"], {"num": 1, "str": -1})

    def test_record_miss_decrements_and_clears_streak(self) -> None:
        state = {
            "squats": {"num": 8, "str": 1},
            "unsaved": [],
        }

        record_miss(state, "squats")

        self.assertEqual(state["squats"], {"num": 7, "str": 0})

    def test_record_miss_does_not_drop_target_below_minimum(self) -> None:
        state = {
            "squats": {"num": 1, "str": 0},
            "unsaved": [],
        }

        record_miss(state, "squats")

        self.assertEqual(state["squats"], {"num": 1, "str": 0})

    def test_replace_unsaved_for_date_replaces_existing_entries_and_sorts(self) -> None:
        state = {
            "push ups": {"num": 10, "str": 0},
            "sit ups": {"num": 10, "str": 0},
            "squats": {"num": 10, "str": 0},
            "unsaved": [
                ["2026-04-20", "push ups", 0],
                ["2026-04-18", "sit ups", 0],
                ["2026-04-20", "squats", 0],
            ],
        }

        replace_unsaved_for_date(state, "2026-04-20", ["break", "push ups"])

        self.assertEqual(
            state["unsaved"],
            [
                ["2026-04-18", "sit ups", 0],
                ["2026-04-20", "push ups", 0],
            ],
        )


class _FixedUnitRandom:
    def __init__(self, values: list[float]) -> None:
        self.values = values
        self.index = 0

    def uniform(self, low: float, high: float) -> float:
        self.assert_bounds(low, high)
        value = self.values[self.index]
        self.index += 1
        return value

    @staticmethod
    def assert_bounds(low: float, high: float) -> None:
        if (low, high) != (0.0, 1.0):
            raise AssertionError(f"expected unit interval bounds, got {(low, high)}")


if __name__ == "__main__":
    unittest.main()
