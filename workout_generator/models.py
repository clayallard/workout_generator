"""Shared data models for the workout generator app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ScheduleDay:
    date: date
    type: str
    details: list[str]


@dataclass(frozen=True)
class PreworkSlot:
    slot: int
    exercise: str
    target: int | None


@dataclass(frozen=True)
class PreworkPlan:
    date: date
    slots: list[PreworkSlot]


@dataclass(frozen=True)
class GeneratedWorkout:
    date: date
    schedule_type: str
    schedule_details: list[str]
    note: str
    content: str
    file_path: Path


@dataclass(frozen=True)
class FeedbackRecord:
    text: str
    date_start: date | None
    date_end: date | None
    completion: str = ""
    difficulty: str = ""
    enjoyment: str = ""
    remembered: bool = False


@dataclass(frozen=True)
class DuePreworkItem:
    date: date
    slot: int
    exercise: str
    target: int
