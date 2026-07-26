"""Project path helpers."""

from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
CONTEXT_ROOT = PROJECT_ROOT / "context"
DATA_ROOT = PROJECT_ROOT / "data"
RUNTIME_ROOT = DATA_ROOT
GENERATED_WORKOUT_ROOT = RUNTIME_ROOT / "generated_workouts"
DEFAULT_DB_PATH = RUNTIME_ROOT / "workout.sqlite3"
AGENT_UPDATE_ROOT = PROJECT_ROOT / ".agent_updates"


def ensure_runtime_dirs() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    GENERATED_WORKOUT_ROOT.mkdir(parents=True, exist_ok=True)
