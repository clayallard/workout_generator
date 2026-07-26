from __future__ import annotations

from datetime import date
import unittest

import numpy as np

from workout_generator.schedule import (
    cycle_day_for_day,
    is_rollover_day,
    is_valid_schedule_combo,
    version_for_day,
    workout_structure_generator,
)


def _high_level_category(workout_type: str) -> str:
    if workout_type in {"run", "gym", "off"}:
        return workout_type
    return "both"


class ScheduleTests(unittest.TestCase):
    def test_version_for_day_uses_four_month_blocks(self) -> None:
        self.assertEqual(version_for_day(date(2026, 1, 1)), "2026-1")
        self.assertEqual(version_for_day(date(2026, 4, 30)), "2026-1")
        self.assertEqual(version_for_day(date(2026, 5, 1)), "2026-2")
        self.assertEqual(version_for_day(date(2026, 8, 31)), "2026-2")
        self.assertEqual(version_for_day(date(2026, 9, 1)), "2026-3")

    def test_rollover_days_match_legacy_schedule_resets(self) -> None:
        self.assertTrue(is_rollover_day(date(2026, 1, 1)))
        self.assertTrue(is_rollover_day(date(2026, 5, 1)))
        self.assertTrue(is_rollover_day(date(2026, 9, 1)))
        self.assertFalse(is_rollover_day(date(2026, 4, 30)))

    def test_cycle_day_for_day_wraps_every_fourteen_days(self) -> None:
        self.assertEqual(cycle_day_for_day(date(2023, 5, 28)), 0)
        self.assertEqual(cycle_day_for_day(date(2023, 6, 10)), 13)
        self.assertEqual(cycle_day_for_day(date(2023, 6, 11)), 0)

    def test_generated_schedule_respects_invariants_and_counts(self) -> None:
        for seed in range(50):
            structure = workout_structure_generator(np.random.RandomState(seed))
            combo = [structure[str(index)]["type"] for index in range(14)]

            self.assertTrue(is_valid_schedule_combo(combo), msg=f"seed {seed} produced invalid combo {combo}")
            self.assertEqual(sum(workout_type == "off" for workout_type in combo), 4)
            self.assertEqual(sum(workout_type == "run" for workout_type in combo), 4)
            self.assertEqual(sum(workout_type == "gym" for workout_type in combo), 4)
            self.assertEqual(sum("run" in workout_type and "gym" in workout_type for workout_type in combo), 2)
            self.assertTrue(all(structure[str(index)]["details"] for index in range(14)))

    def test_generated_schedule_includes_subtype_details(self) -> None:
        structure = workout_structure_generator(np.random.RandomState(0))
        allowed_details = {
            "run": {"easy run", "intervals", "tempo run", "long run"},
            "gym": {"full-body strength", "lower strength", "upper strength", "conditioning"},
            "off": {"full rest", "mobility", "easy walk", "stretch"},
            "run/gym": {"run focus", "strength support"},
            "gym/run": {"strength focus", "run finish"},
        }

        for index in range(14):
            workout_type = structure[str(index)]["type"]
            details = structure[str(index)]["details"]
            self.assertGreaterEqual(len(details), 1)
            self.assertTrue(set(details).issubset(allowed_details[workout_type]))

    def test_pure_schedule_days_get_varied_details(self) -> None:
        structure = workout_structure_generator(np.random.RandomState(1))
        for workout_type in ("run", "gym", "off"):
            details = [
                structure[str(index)]["details"][0]
                for index in range(14)
                if structure[str(index)]["type"] == workout_type
            ]
            self.assertEqual(len(details), 4)
            self.assertEqual(len(set(details)), 4)

    def test_combined_schedule_details_follow_order(self) -> None:
        for seed in range(20):
            structure = workout_structure_generator(np.random.RandomState(seed))
            for index in range(14):
                day = structure[str(index)]
                if day["type"] == "run/gym":
                    self.assertEqual(day["details"], ["run focus", "strength support"])
                if day["type"] == "gym/run":
                    self.assertEqual(day["details"], ["strength focus", "run finish"])

    def test_weeks_share_the_same_high_level_pattern(self) -> None:
        for seed in range(50):
            structure = workout_structure_generator(np.random.RandomState(seed))
            combo = [structure[str(index)]["type"] for index in range(14)]

            week_one = [_high_level_category(workout_type) for workout_type in combo[:7]]
            week_two = [_high_level_category(workout_type) for workout_type in combo[7:]]
            self.assertEqual(week_one, week_two)

            combined_days = [index for index, workout_type in enumerate(combo) if "run" in workout_type and "gym" in workout_type]
            self.assertEqual(len(combined_days), 2)
            self.assertEqual(combined_days[1] - combined_days[0], 7)

    def test_combined_day_order_can_vary_between_weeks(self) -> None:
        found_different_order = False
        for seed in range(200):
            structure = workout_structure_generator(np.random.RandomState(seed))
            combo = [structure[str(index)]["type"] for index in range(14)]
            combined_days = [index for index, workout_type in enumerate(combo) if "run" in workout_type and "gym" in workout_type]
            if combo[combined_days[0]] != combo[combined_days[1]]:
                found_different_order = True
                break

        self.assertTrue(found_different_order)

    def test_version_for_day_changes_across_may_boundary(self) -> None:
        days = [date(2026, 4, 29), date(2026, 4, 30), date(2026, 5, 1), date(2026, 5, 2)]
        versions = [version_for_day(day) for day in days]
        self.assertEqual(versions, ["2026-1", "2026-1", "2026-2", "2026-2"])


if __name__ == "__main__":
    unittest.main()
