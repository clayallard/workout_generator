"""Core schedule generation helpers."""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict

import numpy as np


class ScheduledDay(TypedDict):
    type: str
    details: list[str]


ScheduleStructure = dict[str, ScheduledDay]

REFERENCE_DATE = date(year=2023, month=5, day=28)
ROLLOVER_MONTH_DAYS = frozenset({"0101", "0501", "0901"})
_RUN_DETAILS = ("easy run", "intervals", "tempo run", "long run")
_GYM_DETAILS = ("full-body strength", "lower strength", "upper strength", "conditioning")
_OFF_DETAILS = ("full rest", "mobility", "easy walk", "stretch")
_COMBINED_DETAILS = {
    "run/gym": ("run focus", "strength support"),
    "gym/run": ("strength focus", "run finish"),
}


def is_valid_schedule_combo(combo: list[str]) -> bool:
    """Return whether the 14-day schedule rules are satisfied."""

    streak_run = streak_lift = streak_rest = no_run = no_lift = 0
    for workout_type in combo + combo[:3]:
        no_run += 1
        no_lift += 1

        if workout_type == "off":
            streak_rest += 1
            streak_run = streak_lift = 0
            if streak_rest >= 3 or max(no_run, no_lift) >= 3:
                return False
            continue

        streak_rest = 0
        streak_run += 1
        streak_lift += 1

        if "run" not in workout_type:
            streak_run = 0
        else:
            no_run = 0

        if "gym" not in workout_type:
            streak_lift = 0
        else:
            no_lift = 0

        if max(streak_lift, streak_run, streak_rest, no_lift, no_run) >= 3:
            return False
    return True


def _create_weekly_schedule(np_random: Any = np.random) -> list[str]:
    """Create the weekly-aligned high-level schedule."""

    workout_types = [workout_type for workout_type in ["run", "gym", "off"] for _ in range(2)] + ["both"]
    combined_orders = np_random.choice(["run/gym", "gym/run"], size=2)
    np_random.shuffle(workout_types)
    workout_schedule = workout_types * 2
    combined_index = workout_schedule.index("both")
    workout_schedule[combined_index] = str(combined_orders[0])
    workout_schedule[combined_index + 7] = str(combined_orders[1])
    return workout_schedule


def workout_structure_generator(np_random: Any = np.random) -> ScheduleStructure:
    """Generate the 14-day structure with high-level day types and subtype hints."""

    if np_random.random() < 1:
        workout_types = _create_weekly_schedule(np_random)
        while not is_valid_schedule_combo(workout_types):
            workout_types = _create_weekly_schedule(np_random)
    else:
        workout_types = [workout_type for workout_type in ["run", "gym", "off"] for _ in range(4)] + [
            "run/gym",
            "gym/run",
        ]
        np_random.shuffle(workout_types)
        while not is_valid_schedule_combo(workout_types):
            np_random.shuffle(workout_types)

    structure: ScheduleStructure = {
        str(index): {"type": workout_type, "details": []}
        for index, workout_type in enumerate(workout_types)
    }
    return add_schedule_details(structure, np_random)


def add_schedule_details(
    structure: ScheduleStructure,
    np_random: Any = np.random,
) -> ScheduleStructure:
    """Return a copy of a schedule structure with missing subtype details filled."""

    detail_assigner = _ScheduleDetailAssigner(np_random)
    updated: ScheduleStructure = {}
    for index_key in sorted(structure, key=int):
        day = structure[index_key]
        existing_details = [str(detail) for detail in day.get("details", []) if str(detail)]
        updated[index_key] = {
            "type": str(day["type"]),
            "details": existing_details or detail_assigner.details_for(str(day["type"])),
        }
    return updated


class _ScheduleDetailAssigner:
    def __init__(self, np_random: Any) -> None:
        self.run_details = _shuffled_list(_RUN_DETAILS, np_random)
        self.gym_details = _shuffled_list(_GYM_DETAILS, np_random)
        self.off_details = _shuffled_list(_OFF_DETAILS, np_random)
        self.run_index = 0
        self.gym_index = 0
        self.off_index = 0

    def details_for(self, workout_type: str) -> list[str]:
        if workout_type == "run":
            return [self._next_run_detail()]
        if workout_type == "gym":
            return [self._next_gym_detail()]
        if workout_type == "off":
            return [self._next_off_detail()]
        if workout_type in _COMBINED_DETAILS:
            return list(_COMBINED_DETAILS[workout_type])
        return []

    def _next_run_detail(self) -> str:
        detail = self.run_details[self.run_index % len(self.run_details)]
        self.run_index += 1
        return detail

    def _next_gym_detail(self) -> str:
        detail = self.gym_details[self.gym_index % len(self.gym_details)]
        self.gym_index += 1
        return detail

    def _next_off_detail(self) -> str:
        detail = self.off_details[self.off_index % len(self.off_details)]
        self.off_index += 1
        return detail


def _shuffled_list(values: tuple[str, ...], np_random: Any) -> list[str]:
    shuffled = list(values)
    np_random.shuffle(shuffled)
    return shuffled


def version_for_day(day: date) -> str:
    """Return the four-month schedule version key."""

    return day.strftime("%Y") + "-" + str(int((int(day.strftime("%m")) - 1) / 4) + 1)


def cycle_day_for_day(day: date, reference_date: date = REFERENCE_DATE) -> int:
    """Return the day index inside the repeating 14-day cycle."""

    return (day - reference_date).days % 14


def is_rollover_day(day: date) -> bool:
    """Return whether the day starts a new four-month schedule block."""

    return day.strftime("%m%d") in ROLLOVER_MONTH_DAYS
