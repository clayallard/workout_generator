"""SQLite-backed storage for the workout generator app."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from workout_generator.paths import DEFAULT_DB_PATH, ensure_runtime_dirs


DEFAULT_PREWORK_PROGRESS = {
    "push ups": {"current_target": 65, "streak": 0},
    "sit ups": {"current_target": 77, "streak": 0},
    "squats": {"current_target": 52, "streak": 0},
}


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH

    def initialize(self) -> None:
        ensure_runtime_dirs()
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schedule_cycles (
                    version TEXT PRIMARY KEY,
                    structure_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prework_progress (
                    exercise TEXT PRIMARY KEY,
                    current_target INTEGER NOT NULL,
                    streak INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prework_assignments (
                    date TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    exercise TEXT NOT NULL,
                    target INTEGER,
                    PRIMARY KEY (date, slot)
                );

                CREATE TABLE IF NOT EXISTS prework_assignment_status (
                    date TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    source_text TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (date, slot)
                );

                CREATE TABLE IF NOT EXISTS prework_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    exercise TEXT NOT NULL,
                    target INTEGER,
                    outcome TEXT NOT NULL,
                    source_text TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS generated_workouts (
                    date TEXT PRIMARY KEY,
                    schedule_type TEXT NOT NULL,
                    schedule_details_json TEXT NOT NULL,
                    note TEXT NOT NULL,
                    content TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_text TEXT NOT NULL,
                    date_start TEXT,
                    date_end TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS coaching_memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_date TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workout_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workout_revision_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    base_content TEXT NOT NULL,
                    base_note TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    applied_at TEXT
                );

                CREATE TABLE IF NOT EXISTS workout_revision_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    user_text TEXT NOT NULL,
                    assistant_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES workout_revision_threads(id)
                );
                """
            )
            _ensure_columns(
                connection,
                "feedback_entries",
                {
                    "completion": "TEXT",
                    "difficulty": "TEXT",
                    "enjoyment": "TEXT",
                },
            )
            _ensure_columns(
                connection,
                "workout_questions",
                {"parent_id": "INTEGER"},
            )
            _ensure_columns(
                connection,
                "prework_assignments",
                {"target": "INTEGER"},
            )
            _ensure_columns(
                connection,
                "prework_logs",
                {"target": "INTEGER"},
            )
            existing_count = connection.execute("SELECT COUNT(*) FROM prework_progress").fetchone()[0]
            if existing_count == 0:
                progress = DEFAULT_PREWORK_PROGRESS.copy()
                connection.executemany(
                    """
                    INSERT INTO prework_progress (exercise, current_target, streak)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (exercise, values["current_target"], values["streak"])
                        for exercise, values in progress.items()
                    ],
                )

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def get_setting(self, key: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _timestamp()),
            )

    def get_schedule_structure(self, version: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT structure_json FROM schedule_cycles WHERE version = ?",
                (version,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["structure_json"])

    def save_schedule_structure(self, version: str, structure: dict[str, Any]) -> None:
        now = _timestamp()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO schedule_cycles (version, structure_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(version) DO UPDATE SET
                    structure_json = excluded.structure_json
                """,
                (version, json.dumps(structure), now),
            )

    def list_schedule_versions(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT version
                FROM schedule_cycles
                ORDER BY version
                """
            ).fetchall()
        return [str(row["version"]) for row in rows]

    def delete_schedule_versions(self, versions: list[str]) -> int:
        if not versions:
            return 0
        placeholders = ", ".join("?" for _ in versions)
        with self.connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM schedule_cycles WHERE version IN ({placeholders})",
                versions,
            )
        return int(cursor.rowcount)

    def get_prework_progress(self) -> dict[str, dict[str, int]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT exercise, current_target, streak
                FROM prework_progress
                ORDER BY exercise
                """
            ).fetchall()
        return {
            row["exercise"]: {
                "current_target": int(row["current_target"]),
                "streak": int(row["streak"]),
            }
            for row in rows
        }

    def set_prework_progress(self, exercise: str, current_target: int, streak: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE prework_progress
                SET current_target = ?, streak = ?
                WHERE exercise = ?
                """,
                (current_target, streak, exercise),
            )

    def get_prework_assignments(self, date_str: str) -> list[dict[str, Any]] | None:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT slot, exercise, target
                FROM prework_assignments
                WHERE date = ?
                ORDER BY slot
                """,
                (date_str,),
            ).fetchall()
        if not rows:
            return None
        return [
            {
                "slot": int(row["slot"]),
                "exercise": str(row["exercise"]),
                "target": None if row["target"] is None else int(row["target"]),
            }
            for row in rows
        ]

    def save_prework_assignments(
        self,
        date_str: str,
        assignments: list[str],
        targets: dict[str, int] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM prework_assignments WHERE date = ?", (date_str,))
            connection.execute("DELETE FROM prework_assignment_status WHERE date = ?", (date_str,))
            connection.executemany(
                """
                INSERT INTO prework_assignments (date, slot, exercise, target)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        date_str,
                        index,
                        assignment,
                        None if assignment == "break" or targets is None else targets.get(assignment),
                    )
                    for index, assignment in enumerate(assignments)
                ],
            )

    def get_due_prework_assignments(self, through_date_str: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT a.date, a.slot, a.exercise, a.target
                FROM prework_assignments AS a
                LEFT JOIN prework_assignment_status AS s
                    ON s.date = a.date AND s.slot = a.slot
                WHERE a.date <= ?
                  AND a.exercise != 'break'
                  AND s.date IS NULL
                ORDER BY a.date, a.slot
                """,
                (through_date_str,),
            ).fetchall()
        return rows

    def mark_prework_assignment(self, date_str: str, slot: int, outcome: str, source_text: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO prework_assignment_status (date, slot, outcome, source_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date, slot) DO UPDATE SET
                    outcome = excluded.outcome,
                    source_text = excluded.source_text,
                    created_at = excluded.created_at
                """,
                (date_str, slot, outcome, source_text, _timestamp()),
            )

    def add_prework_log(
        self,
        date_str: str,
        exercise: str,
        outcome: str,
        source_text: str = "",
        target: int | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO prework_logs (date, exercise, target, outcome, source_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (date_str, exercise, target, outcome, source_text, _timestamp()),
            )

    def list_prework_logs(self, limit: int = 10) -> list[dict[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT date, exercise, target, outcome, source_text, created_at
                FROM prework_logs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "date": str(row["date"]),
                "exercise": str(row["exercise"]),
                "target": "" if row["target"] is None else str(row["target"]),
                "outcome": str(row["outcome"]),
                "source_text": str(row["source_text"] or ""),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def get_generated_workout(self, date_str: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT date, schedule_type, schedule_details_json, note, content, file_path
                FROM generated_workouts
                WHERE date = ?
                """,
                (date_str,),
            ).fetchone()
        return row

    def list_generated_workouts_after(self, after_date_str: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT date, file_path
                FROM generated_workouts
                WHERE date > ?
                ORDER BY date
                """,
                (after_date_str,),
            ).fetchall()
        return rows

    def delete_generated_workouts_after(self, after_date_str: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM generated_workouts
                WHERE date > ?
                """,
                (after_date_str,),
            )
        return int(cursor.rowcount)

    def save_generated_workout(
        self,
        date_str: str,
        schedule_type: str,
        schedule_details: list[str],
        note: str,
        content: str,
        file_path: str,
    ) -> None:
        now = _timestamp()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO generated_workouts (
                    date,
                    schedule_type,
                    schedule_details_json,
                    note,
                    content,
                    file_path,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    schedule_type = excluded.schedule_type,
                    schedule_details_json = excluded.schedule_details_json,
                    note = excluded.note,
                    content = excluded.content,
                    file_path = excluded.file_path,
                    updated_at = excluded.updated_at
                """,
                (
                    date_str,
                    schedule_type,
                    json.dumps(schedule_details),
                    note,
                    content,
                    file_path,
                    now,
                    now,
                ),
            )

    def list_recent_generated_workouts(
        self,
        limit: int = 5,
        before_date_str: str | None = None,
    ) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT date, schedule_type, note, content
                FROM generated_workouts
                WHERE (? IS NULL OR date < ?)
                  AND schedule_type != 'off'
                ORDER BY date DESC
                LIMIT ?
                """,
                (before_date_str, before_date_str, limit),
            ).fetchall()
        return rows

    def list_feedback_entries(self, after_date_str: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_text, date_start, date_end, completion, difficulty, enjoyment, created_at
                FROM feedback_entries
                WHERE (? IS NULL OR created_at >= ?)
                ORDER BY created_at DESC
                """,
                (after_date_str, after_date_str),
            ).fetchall()
        return rows

    def list_feedback_for_date(self, date_str: str) -> list[dict[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_text, date_start, date_end, completion, difficulty, enjoyment, created_at
                FROM feedback_entries
                WHERE (date_start IS NULL AND date_end IS NULL)
                   OR (date_start <= ? AND date_end >= ?)
                   OR (date_start = ? AND date_end IS NULL)
                   OR (date_end = ? AND date_start IS NULL)
                ORDER BY created_at DESC
                """,
                (date_str, date_str, date_str, date_str),
            ).fetchall()
        return [
            {
                "source_text": str(row["source_text"]),
                "date_start": str(row["date_start"] or ""),
                "date_end": str(row["date_end"] or ""),
                "completion": str(row["completion"] or ""),
                "difficulty": str(row["difficulty"] or ""),
                "enjoyment": str(row["enjoyment"] or ""),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def add_feedback(
        self,
        source_text: str,
        date_start: str | None,
        date_end: str | None,
        completion: str = "",
        difficulty: str = "",
        enjoyment: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback_entries (
                    source_text,
                    date_start,
                    date_end,
                    completion,
                    difficulty,
                    enjoyment,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (source_text, date_start, date_end, completion, difficulty, enjoyment, _timestamp()),
            )

    def add_coaching_memory(
        self,
        content: str,
        source_type: str = "manual",
        source_date: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO coaching_memory_entries (source_type, source_date, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (source_type, source_date, content, _timestamp()),
            )

    def list_coaching_memory_entries(self) -> list[dict[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_type, source_date, content, created_at
                FROM coaching_memory_entries
                ORDER BY created_at, id
                """
            ).fetchall()
        return [
            {
                "source_type": str(row["source_type"]),
                "source_date": str(row["source_date"] or ""),
                "content": str(row["content"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def add_workout_question(
        self,
        date_str: str,
        question: str,
        answer: str,
        parent_id: int | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO workout_questions (date, question, answer, parent_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date_str, question, answer, parent_id, _timestamp()),
            )
        return int(cursor.lastrowid)

    def list_workout_questions(self, date_str: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, parent_id, question, answer, created_at
                FROM workout_questions
                WHERE date = ?
                ORDER BY id
                """,
                (date_str,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "parent_id": None if row["parent_id"] is None else int(row["parent_id"]),
                "question": str(row["question"]),
                "answer": str(row["answer"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def list_workout_question_thread(self, date_str: str, root_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, parent_id, question, answer, created_at
                FROM workout_questions
                WHERE date = ? AND (id = ? OR parent_id = ?)
                ORDER BY id
                """,
                (date_str, root_id, root_id),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "parent_id": None if row["parent_id"] is None else int(row["parent_id"]),
                "question": str(row["question"]),
                "answer": str(row["answer"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def create_workout_revision_thread(self, date_str: str, base_content: str, base_note: str) -> int:
        now = _timestamp()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO workout_revision_threads (
                    date, base_content, base_note, status, created_at, updated_at
                )
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (date_str, base_content, base_note, now, now),
            )
        return int(cursor.lastrowid)

    def get_active_workout_revision_thread(self, date_str: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, date, base_content, base_note, status, created_at, updated_at, applied_at
                FROM workout_revision_threads
                WHERE date = ? AND status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (date_str,),
            ).fetchone()
        return _revision_thread_dict(row)

    def get_latest_workout_revision_thread(self, date_str: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, date, base_content, base_note, status, created_at, updated_at, applied_at
                FROM workout_revision_threads
                WHERE date = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (date_str,),
            ).fetchone()
        return _revision_thread_dict(row)

    def add_workout_revision_message(self, thread_id: int, user_text: str, assistant_text: str) -> int:
        now = _timestamp()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO workout_revision_messages (thread_id, user_text, assistant_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (thread_id, user_text, assistant_text, now),
            )
            connection.execute(
                "UPDATE workout_revision_threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )
        return int(cursor.lastrowid)

    def list_workout_revision_messages(self, thread_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_text, assistant_text, created_at
                FROM workout_revision_messages
                WHERE thread_id = ?
                ORDER BY id
                """,
                (thread_id,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "user_text": str(row["user_text"]),
                "assistant_text": str(row["assistant_text"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def set_workout_revision_status(self, thread_id: int, status: str) -> None:
        now = _timestamp()
        applied_at = now if status == "applied" else None
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE workout_revision_threads
                SET status = ?, updated_at = ?, applied_at = ?
                WHERE id = ?
                """,
                (status, now, applied_at, thread_id),
            )

    def delete_prework_future(self, after_date_str: str) -> dict[str, int]:
        with self.connect() as connection:
            status_cursor = connection.execute(
                """
                DELETE FROM prework_assignment_status
                WHERE date > ?
                """,
                (after_date_str,),
            )
            assignment_cursor = connection.execute(
                """
                DELETE FROM prework_assignments
                WHERE date > ?
                """,
                (after_date_str,),
            )
            log_cursor = connection.execute(
                """
                DELETE FROM prework_logs
                WHERE date > ?
                """,
                (after_date_str,),
            )
        return {
            "assignment_status": int(status_cursor.rowcount),
            "assignments": int(assignment_cursor.rowcount),
            "logs": int(log_cursor.rowcount),
        }

    def delete_prework_assignments(self) -> dict[str, int]:
        with self.connect() as connection:
            status_cursor = connection.execute("DELETE FROM prework_assignment_status")
            assignment_cursor = connection.execute("DELETE FROM prework_assignments")
        return {
            "assignment_status": int(status_cursor.rowcount),
            "assignments": int(assignment_cursor.rowcount),
        }


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _revision_thread_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "date": str(row["date"]),
        "base_content": str(row["base_content"]),
        "base_note": str(row["base_note"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "applied_at": str(row["applied_at"] or ""),
    }


def _ensure_columns(connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing_columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
