"""Helpers for parsing user notes and freeform feedback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re


_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DURATION_PATTERN = re.compile(r"\b(\d{1,3})\s*(?:min|mins|minute|minutes)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RequestContext:
    raw_text: str
    duration_minutes: int | None
    mentions_travel: bool
    mentions_injury: bool
    crowded_gym: bool
    home_only: bool
    minimal_equipment: bool


def parse_request_context(text: str | None) -> RequestContext:
    note = (text or "").strip()
    lowered = note.lower()
    duration_match = _DURATION_PATTERN.search(lowered)
    duration_minutes = int(duration_match.group(1)) if duration_match else None
    if duration_minutes is None and any(keyword in lowered for keyword in ("short", "shorter", "quick")):
        duration_minutes = 30

    def has_any(*keywords: str) -> bool:
        return any(keyword in lowered for keyword in keywords)

    return RequestContext(
        raw_text=note,
        duration_minutes=duration_minutes,
        mentions_travel=has_any("travel", "vacation", "hotel", "away"),
        mentions_injury=has_any("injury", "hurt", "pain", "sore", "strained", "strain", "tweak"),
        crowded_gym=has_any("crowded", "packed", "busy gym"),
        home_only=has_any("home", "no gym", "garage"),
        minimal_equipment=has_any("hotel", "travel", "bodyweight", "minimal equipment", "no equipment"),
    )


def extract_dates(text: str) -> list[date]:
    dates: list[date] = []
    for match in _DATE_PATTERN.findall(text):
        try:
            dates.append(datetime.strptime(match, "%Y-%m-%d").date())
        except ValueError:
            continue
    return sorted(set(dates))


def extract_date_span(text: str) -> tuple[date | None, date | None]:
    dates = extract_dates(text)
    if not dates:
        return None, None
    return dates[0], dates[-1]
