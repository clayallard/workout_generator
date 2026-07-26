"""Core pre-workout assignment and progression helpers."""

from __future__ import annotations

from typing import Any

import numpy as np

PRE_WORKOUT_CHOICES = ("push ups", "sit ups", "squats", "break")
PRE_WORKOUT_PROBABILITIES = (1 / 4, 1 / 8, 1 / 8, 1 / 2)
_PUSH_UP_CUTOFF = PRE_WORKOUT_PROBABILITIES[0]
_SIT_UP_CUTOFF = _PUSH_UP_CUTOFF + PRE_WORKOUT_PROBABILITIES[1]
_SQUAT_CUTOFF = _SIT_UP_CUTOFF + PRE_WORKOUT_PROBABILITIES[2]

# Targets never drop below this on a missed or failed attempt.
MINIMUM_TARGET = 1


def generate_daily_assignments(np_random: Any = np.random) -> list[str]:
    """Generate the two daily morning-routine assignments."""

    return [assignment_for_preworkout_roll(_random_unit_interval(np_random)) for _ in range(2)]


def assignment_for_preworkout_roll(roll: float) -> str:
    """Map one continuous [0, 1] roll to a pre-workout assignment."""

    if roll < 0 or roll > 1:
        raise ValueError("pre-workout roll must be in [0, 1]")
    if roll < _PUSH_UP_CUTOFF:
        return "push ups"
    if roll < _SIT_UP_CUTOFF:
        return "sit ups"
    if roll < _SQUAT_CUTOFF:
        return "squats"
    return "break"


def _random_unit_interval(np_random: Any) -> float:
    return float(np_random.uniform(0.0, 1.0))


def record_completion(pre_workout: dict[str, Any], workout_name: str) -> None:
    """Record a completion; two in a row raise the target by one.

    The streak is signed: a completion after a failed streak (-1) flips it to 1,
    and the streak returns to 0 only when landing on a fresh target.
    """

    if pre_workout[workout_name]["str"] == 1:
        pre_workout[workout_name]["num"] += 1
        pre_workout[workout_name]["str"] = 0
        return
    pre_workout[workout_name]["str"] = 1


def record_failure(pre_workout: dict[str, Any], workout_name: str) -> None:
    """Record a tried-but-failed attempt; two in a row lower the target by one.

    Mirrors record_completion with a signed streak: the first failure sets the
    streak to -1, and a second consecutive failure lowers the target and resets
    the streak to 0. The streak is 0 only when sitting on a fresh target, so at
    the minimum target (where the number cannot drop) it stays at -1.
    """

    if pre_workout[workout_name]["str"] == -1:
        new_target = max(MINIMUM_TARGET, pre_workout[workout_name]["num"] - 1)
        if new_target != pre_workout[workout_name]["num"]:
            pre_workout[workout_name]["num"] = new_target
            pre_workout[workout_name]["str"] = 0
        return
    pre_workout[workout_name]["str"] = -1


def record_miss(pre_workout: dict[str, Any], workout_name: str) -> None:
    """Record a not-attempted (did-not-do) miss: lower the target now and clear the streak."""

    pre_workout[workout_name]["str"] = 0
    pre_workout[workout_name]["num"] = max(MINIMUM_TARGET, pre_workout[workout_name]["num"] - 1)


def replace_unsaved_for_date(
    pre_workout: dict[str, Any],
    date_str: str,
    assignments: list[str],
) -> None:
    """Replace queued pre-work assignments for a specific date."""

    pre_workout["unsaved"] = [
        queued_assignment
        for queued_assignment in pre_workout["unsaved"]
        if queued_assignment[0] != date_str
    ]
    for assignment in assignments:
        if assignment == "break":
            continue
        pre_workout["unsaved"].append([date_str, assignment, 0])
    pre_workout["unsaved"].sort(key=lambda queued_assignment: queued_assignment[0])
