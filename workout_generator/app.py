"""High-level application service for the workout generator."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import secrets
from typing import Any

import numpy as np

from workout_generator.generator import answer_workout_question as generate_workout_answer
from workout_generator.generator import discuss_workout_revision as generate_revision_discussion
from workout_generator.generator import generate_workout_markdown
from workout_generator.generator import revise_workout_markdown
from workout_generator.generator import summarize_app_request
from workout_generator.markdown import clean_workout_markdown, render_workout_document
from workout_generator.models import DuePreworkItem, FeedbackRecord, GeneratedWorkout, PreworkPlan, PreworkSlot, ScheduleDay
from workout_generator.notes import extract_date_span
from workout_generator.notifications import NTFY_SERVER, publish_html_attachment, publish_markdown
from workout_generator.paths import AGENT_UPDATE_ROOT, GENERATED_WORKOUT_ROOT, PROJECT_ROOT, ensure_runtime_dirs
from workout_generator.preworkout import generate_daily_assignments, record_completion, record_failure, record_miss
from workout_generator.schedule import add_schedule_details, cycle_day_for_day, version_for_day, workout_structure_generator
from workout_generator.storage import Storage


_PREFERENCES_FILE = PROJECT_ROOT / "user_profile" / "preferences.md"

_COMPLETION_VALUES = {"", "completed", "partial", "missed"}
_DIFFICULTY_VALUES = {"", "easy", "as_expected", "hard"}
_ENJOYMENT_VALUES = {"", "liked", "neutral", "disliked"}
_NTFY_TOPIC_SETTING = "ntfy_topic"
_NTFY_TOPIC_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_THEME_SETTING = "theme"
_THEME_VALUES = {"light", "dark"}


class WorkoutApp:
    def __init__(
        self,
        storage: Storage | None = None,
        generated_workout_root: Path | None = None,
        app_request_root: Path | None = None,
        np_random: Any = np.random,
    ) -> None:
        self.storage = storage or Storage()
        self.generated_workout_root = generated_workout_root or GENERATED_WORKOUT_ROOT
        self.app_request_root = app_request_root or AGENT_UPDATE_ROOT
        self.np_random = np_random
        self.storage.initialize()
        ensure_runtime_dirs()
        self.generated_workout_root.mkdir(parents=True, exist_ok=True)

    def get_schedule_day(self, target_date: date) -> ScheduleDay:
        version = version_for_day(target_date)
        structure = self._ensure_schedule_version(version)
        cycle_index = cycle_day_for_day(target_date)
        raw_day = structure[str(cycle_index)]
        return ScheduleDay(
            date=target_date,
            type=str(raw_day["type"]),
            details=[str(item) for item in raw_day["details"]],
        )

    def get_schedule_window(self, start_date: date, days: int) -> list[ScheduleDay]:
        return [self.get_schedule_day(start_date + timedelta(days=offset)) for offset in range(days)]

    def _ensure_schedule_version(self, version: str) -> dict[str, Any]:
        structure = self.storage.get_schedule_structure(version)
        if structure is None:
            structure = workout_structure_generator(self.np_random)
            self.storage.save_schedule_structure(version, structure)
        elif _schedule_has_missing_details(structure):
            structure = add_schedule_details(structure, self.np_random)
            self.storage.save_schedule_structure(version, structure)
        return structure

    def get_prework_plan(self, target_date: date) -> PreworkPlan:
        date_str = target_date.isoformat()
        assignments = self.storage.get_prework_assignments(date_str)
        progress = self.storage.get_prework_progress()
        if assignments is None:
            generated_assignments = generate_daily_assignments(self.np_random)
            self.storage.save_prework_assignments(
                date_str,
                generated_assignments,
                _current_prework_targets(progress),
            )
            assignments = self.storage.get_prework_assignments(date_str)
        if assignments is None:
            assignments = []

        slots = [
            PreworkSlot(
                slot=int(assignment["slot"]) + 1,
                exercise=str(assignment["exercise"]),
                target=_assignment_target(assignment, progress),
            )
            for assignment in assignments
        ]
        return PreworkPlan(date=target_date, slots=slots)

    def log_prework(
        self,
        target_date: date,
        done: list[str] | None = None,
        missed: list[str] | None = None,
        failed: list[str] | None = None,
        skipped: list[str] | None = None,
        source_text: str = "",
    ) -> None:
        progress = self.storage.get_prework_progress()
        legacy_state = {
            exercise: {
                "num": values["current_target"],
                "str": values["streak"],
            }
            for exercise, values in progress.items()
        }

        date_str = target_date.isoformat()
        for exercise in done or []:
            target = int(legacy_state[exercise]["num"])
            record_completion(legacy_state, exercise)
            self.storage.add_prework_log(date_str, exercise, "done", source_text, target)
        for exercise in missed or []:
            target = int(legacy_state[exercise]["num"])
            record_miss(legacy_state, exercise)
            self.storage.add_prework_log(date_str, exercise, "missed", source_text, target)
        for exercise in failed or []:
            target = int(legacy_state[exercise]["num"])
            record_failure(legacy_state, exercise)
            self.storage.add_prework_log(date_str, exercise, "failed", source_text, target)
        for exercise, values in legacy_state.items():
            self.storage.set_prework_progress(exercise, values["num"], values["str"])

        pending_rows = list(self.storage.get_due_prework_assignments(date_str))
        outcomes = [
            ("done", done or []),
            ("missed", missed or []),
            ("failed", failed or []),
            ("skipped", skipped or []),
        ]
        for outcome, exercises in outcomes:
            for exercise in exercises:
                _mark_first_pending_prework_assignment(
                    self.storage,
                    pending_rows,
                    date_str,
                    exercise,
                    outcome,
                    source_text,
                )

    def get_due_prework_items(self, through_date: date) -> list[DuePreworkItem]:
        progress = self.storage.get_prework_progress()
        return [
            DuePreworkItem(
                date=date.fromisoformat(row["date"]),
                slot=int(row["slot"]) + 1,
                exercise=str(row["exercise"]),
                target=_assignment_target(row, progress) or progress[str(row["exercise"])]["current_target"],
            )
            for row in self.storage.get_due_prework_assignments(through_date.isoformat())
        ]

    def log_prework_assignment(self, item: DuePreworkItem, outcome: str, source_text: str = "") -> None:
        if outcome not in {"done", "missed", "failed", "skipped"}:
            return
        if outcome == "skipped":
            self.storage.mark_prework_assignment(item.date.isoformat(), item.slot - 1, outcome, source_text)
            return
        self._record_prework_assignment_outcome(item, outcome, source_text)
        self.storage.mark_prework_assignment(item.date.isoformat(), item.slot - 1, outcome, source_text)

    def _record_prework_assignment_outcome(
        self,
        item: DuePreworkItem,
        outcome: str,
        source_text: str = "",
    ) -> None:
        progress = self.storage.get_prework_progress()
        legacy_state = {
            exercise: {
                "num": values["current_target"],
                "str": values["streak"],
            }
            for exercise, values in progress.items()
        }
        if outcome == "done":
            record_completion(legacy_state, item.exercise)
        elif outcome == "failed":
            record_failure(legacy_state, item.exercise)
        elif outcome == "missed":
            record_miss(legacy_state, item.exercise)
        else:
            return

        self.storage.add_prework_log(
            item.date.isoformat(),
            item.exercise,
            outcome,
            source_text,
            item.target,
        )
        for exercise, values in legacy_state.items():
            self.storage.set_prework_progress(exercise, values["num"], values["str"])

    def get_or_create_workout(
        self,
        target_date: date,
        note: str = "",
        regenerate: bool = False,
    ) -> GeneratedWorkout:
        date_str = target_date.isoformat()
        requested_note = note.strip()
        existing_workout = self.get_saved_workout(target_date)
        if existing_workout is not None and not regenerate:
            return existing_workout

        schedule_day = self.get_schedule_day(target_date)
        content = generate_workout_markdown(schedule_day, note=note, storage=self.storage)
        return self._save_generated_workout(schedule_day, requested_note, content)

    def _save_generated_workout(
        self,
        schedule_day: ScheduleDay,
        note: str,
        content: str,
    ) -> GeneratedWorkout:
        date_str = schedule_day.date.isoformat()
        file_path = self.generated_workout_root / f"{date_str}.md"
        file_path.write_text(content)
        self.storage.save_generated_workout(
            date_str=date_str,
            schedule_type=schedule_day.type,
            schedule_details=schedule_day.details,
            note=note,
            content=content,
            file_path=str(file_path),
        )
        return GeneratedWorkout(
            date=schedule_day.date,
            schedule_type=schedule_day.type,
            schedule_details=schedule_day.details,
            note=note,
            content=content,
            file_path=file_path,
        )

    def get_saved_workout(self, target_date: date) -> GeneratedWorkout | None:
        existing = self.storage.get_generated_workout(target_date.isoformat())
        if existing is not None:
            return GeneratedWorkout(
                date=target_date,
                schedule_type=str(existing["schedule_type"]),
                schedule_details=json.loads(existing["schedule_details_json"]),
                note=str(existing["note"]),
                content=str(existing["content"]),
                file_path=Path(existing["file_path"]),
            )
        return None

    def revise_workout(self, target_date: date, note: str) -> GeneratedWorkout:
        saved_workout = self.get_saved_workout(target_date)
        if saved_workout is None:
            raise ValueError("Generate a workout for this date before revising it.")
        request = note.strip()
        if not request:
            raise ValueError("Revision request is required.")
        revised_content = revise_workout_markdown(
            saved_workout.content,
            [
                {
                    "user_text": request,
                    "assistant_text": "Apply only this request and preserve everything else exactly.",
                }
            ],
        )
        return self._save_generated_workout(
            self.get_schedule_day(target_date),
            saved_workout.note,
            clean_workout_markdown(revised_content),
        )

    def discuss_workout_revision(self, target_date: date, message: str) -> dict[str, Any]:
        saved_workout = self.get_saved_workout(target_date)
        if saved_workout is None:
            raise ValueError("Generate a workout for this date before discussing a revision.")
        message = message.strip()
        if not message:
            raise ValueError("Revision message is required.")

        date_str = target_date.isoformat()
        thread = self.storage.get_active_workout_revision_thread(date_str)
        if thread is None:
            thread_id = self.storage.create_workout_revision_thread(
                date_str,
                saved_workout.content,
                saved_workout.note,
            )
            thread = self.storage.get_active_workout_revision_thread(date_str)
            if thread is None:
                raise RuntimeError("Could not create the revision discussion.")
        else:
            thread_id = int(thread["id"])

        prior_messages = self.storage.list_workout_revision_messages(thread_id)
        response = generate_revision_discussion(
            workout_content=str(thread["base_content"]),
            message=message,
            prior_messages=prior_messages,
        )
        self.storage.add_workout_revision_message(thread_id, message, response)
        return self.get_workout_revision_thread(target_date) or {}

    def get_workout_revision_thread(self, target_date: date) -> dict[str, Any] | None:
        thread = self.storage.get_latest_workout_revision_thread(target_date.isoformat())
        if thread is None:
            return None
        return {
            **thread,
            "messages": self.storage.list_workout_revision_messages(int(thread["id"])),
        }

    def apply_workout_revision(self, target_date: date, message: str = "") -> GeneratedWorkout:
        date_str = target_date.isoformat()
        final_instruction = message.strip()
        saved_workout = self.get_saved_workout(target_date)
        if saved_workout is None:
            raise ValueError("The saved workout no longer exists.")

        thread = self.storage.get_active_workout_revision_thread(date_str)
        if thread is None:
            if not final_instruction:
                raise ValueError("Type a revision request, or discuss one, before applying.")
            self.storage.create_workout_revision_thread(
                date_str,
                saved_workout.content,
                saved_workout.note,
            )
            thread = self.storage.get_active_workout_revision_thread(date_str)
            if thread is None:
                raise RuntimeError("Could not create the revision discussion.")

        thread_id = int(thread["id"])
        messages = self.storage.list_workout_revision_messages(thread_id)
        if not messages and not final_instruction:
            raise ValueError("Discuss the revision or type a request before applying it.")
        if saved_workout.content != thread["base_content"]:
            raise ValueError("The workout changed after this discussion started. Discard it and start a new revision.")

        revised_content = revise_workout_markdown(
            str(thread["base_content"]),
            messages,
            final_instruction=final_instruction,
        )
        revised = self._save_generated_workout(
            self.get_schedule_day(target_date),
            str(thread["base_note"]),
            clean_workout_markdown(revised_content),
        )
        if final_instruction:
            self.storage.add_workout_revision_message(
                thread_id,
                final_instruction,
                "Applied this instruction to the saved workout.",
            )
        self.storage.set_workout_revision_status(thread_id, "applied")
        return revised

    def discard_workout_revision(self, target_date: date) -> None:
        thread = self.storage.get_active_workout_revision_thread(target_date.isoformat())
        if thread is None:
            raise ValueError("There is no active revision discussion to discard.")
        self.storage.set_workout_revision_status(int(thread["id"]), "discarded")

    def save_preference(self, text: str) -> None:
        entry = f"- {text.strip()}\n"
        if _PREFERENCES_FILE.exists():
            existing = _PREFERENCES_FILE.read_text().rstrip("\n")
            _PREFERENCES_FILE.write_text(existing + "\n" + entry)
        else:
            _PREFERENCES_FILE.write_text(f"# Preferences\n\n{entry}")

    def list_preferences(self) -> list[str]:
        if not _PREFERENCES_FILE.exists():
            return []
        return [line[2:] for line in _PREFERENCES_FILE.read_text().splitlines() if line.startswith("- ")]

    def list_coaching_memory(self) -> list[dict[str, str]]:
        return self.storage.list_coaching_memory_entries()

    def save_app_request(self, text: str) -> Path:
        request_text = text.strip()
        if not request_text:
            raise ValueError("App request text is required.")

        request_dir = self.app_request_root / "requests"
        request_dir.mkdir(parents=True, exist_ok=True)
        _write_agent_update_readme(self.app_request_root)

        created_at = datetime.now().isoformat(timespec="seconds")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_path = request_dir / f"{timestamp}-{secrets.token_hex(3)}.md"
        summary = _summarize_app_request_safely(request_text)
        file_path.write_text(_format_app_request_document(created_at, summary, request_text))
        return file_path

    def get_ntfy_topic(self) -> str:
        topic = self.storage.get_setting(_NTFY_TOPIC_SETTING)
        if topic is None:
            topic = f"workout-{secrets.token_urlsafe(18)}"
            self.storage.set_setting(_NTFY_TOPIC_SETTING, topic)
        return topic

    def set_ntfy_topic(self, topic: str) -> str:
        normalized = topic.strip()
        if not _NTFY_TOPIC_PATTERN.fullmatch(normalized):
            raise ValueError("ntfy topic must be 8-64 characters using only letters, numbers, hyphens, or underscores.")
        self.storage.set_setting(_NTFY_TOPIC_SETTING, normalized)
        return normalized

    def get_theme(self) -> str:
        theme = self.storage.get_setting(_THEME_SETTING)
        if theme in _THEME_VALUES:
            return theme
        return "light"

    def set_theme(self, theme: str) -> str:
        normalized = theme.strip().lower()
        if normalized not in _THEME_VALUES:
            raise ValueError("Theme must be light or dark.")
        self.storage.set_setting(_THEME_SETTING, normalized)
        return normalized

    def get_ntfy_server(self) -> str:
        return NTFY_SERVER

    def send_phone_test(self) -> int:
        return publish_markdown(
            topic=self.get_ntfy_topic(),
            markdown="## Workout Generator\n\nPhone delivery is connected.",
            title="Workout Generator test",
        )

    def send_workout_to_phone(self, target_date: date) -> int:
        saved_workout = self.get_saved_workout(target_date)
        if saved_workout is None:
            raise ValueError("Generate a workout for this date before sending it to your phone.")
        title = f"Workout for {target_date.isoformat()}"
        html = render_workout_document(saved_workout.content, title, saved_workout.note)
        return publish_html_attachment(
            topic=self.get_ntfy_topic(),
            html=html,
            title=title,
            filename=f"workout-{target_date.isoformat()}.html",
        )

    def get_prework_progress(self) -> dict[str, dict[str, int]]:
        return self.storage.get_prework_progress()

    def get_prework_history(self, limit: int = 10) -> list[dict[str, str]]:
        return self.storage.list_prework_logs(limit=limit)

    def list_feedback_for_date(self, target_date: date) -> list[dict[str, str]]:
        return self.storage.list_feedback_for_date(target_date.isoformat())

    def clear_generated_daily_reps(self) -> dict[str, int]:
        return self.storage.delete_prework_assignments()

    def answer_workout_question(
        self,
        target_date: date,
        question: str,
        thread_id: int | None = None,
    ) -> str:
        saved_workout = self.get_saved_workout(target_date)
        if saved_workout is None:
            raise ValueError("Generate a workout for this date before asking questions about it.")
        question = question.strip()
        if not question:
            raise ValueError("Question text is required.")

        prior_questions: list[dict[str, Any]] = []
        if thread_id is not None:
            prior_questions = self.storage.list_workout_question_thread(target_date.isoformat(), thread_id)
            valid_root = (
                prior_questions
                and prior_questions[0]["id"] == thread_id
                and prior_questions[0]["parent_id"] is None
            )
            if not valid_root:
                raise ValueError("Question thread was not found for this workout.")

        return generate_workout_answer(
            workout_content=saved_workout.content,
            question=question,
            prior_questions=prior_questions,
        )

    def save_workout_question(
        self,
        target_date: date,
        question: str,
        answer: str,
        thread_id: int | None = None,
    ) -> int:
        return self.storage.add_workout_question(
            date_str=target_date.isoformat(),
            question=question.strip(),
            answer=answer,
            parent_id=thread_id,
        )

    def list_workout_questions(self, target_date: date) -> list[dict[str, Any]]:
        rows = self.storage.list_workout_questions(target_date.isoformat())
        threads: dict[int, dict[str, Any]] = {}
        for row in rows:
            if row["parent_id"] is None:
                threads[row["id"]] = {**row, "replies": []}
        for row in rows:
            parent_id = row["parent_id"]
            if parent_id in threads:
                threads[parent_id]["replies"].append(row)
        return list(reversed(threads.values()))

    def record_feedback(
        self,
        text: str,
        completion: str = "",
        difficulty: str = "",
        enjoyment: str = "",
        target_date: date | None = None,
        remember: bool = False,
    ) -> FeedbackRecord:
        completion = _normalize_feedback_value(completion, _COMPLETION_VALUES, "completion")
        difficulty = _normalize_feedback_value(difficulty, _DIFFICULTY_VALUES, "difficulty")
        enjoyment = _normalize_feedback_value(enjoyment, _ENJOYMENT_VALUES, "enjoyment")
        has_rating = any((completion, difficulty, enjoyment))
        source_text = text.strip()
        if not source_text and target_date is not None and has_rating:
            source_text = f"{target_date.isoformat()} quick feedback"
        elif not source_text and has_rating:
            source_text = "Quick feedback"
        if not source_text:
            raise ValueError("Feedback requires text or at least one quick rating.")

        start_date, end_date = extract_date_span(source_text)
        if start_date is None and target_date is not None:
            start_date = end_date = target_date
        self.storage.add_feedback(
            source_text=source_text,
            date_start=start_date.isoformat() if start_date else None,
            date_end=end_date.isoformat() if end_date else None,
            completion=completion,
            difficulty=difficulty,
            enjoyment=enjoyment,
        )
        remembered = False
        if remember:
            self.storage.add_coaching_memory(
                content=_format_feedback_memory(source_text, completion, difficulty, enjoyment),
                source_type="feedback",
                source_date=_memory_source_date(start_date, end_date),
            )
            remembered = True
        return FeedbackRecord(
            text=source_text,
            date_start=start_date,
            date_end=end_date,
            completion=completion,
            difficulty=difficulty,
            enjoyment=enjoyment,
            remembered=remembered,
        )

    def clear_future(self, after_date: date) -> dict[str, int]:
        after_date_str = after_date.isoformat()
        generated_rows = self.storage.list_generated_workouts_after(after_date_str)
        removed_files = 0
        for row in generated_rows:
            file_path = Path(str(row["file_path"]))
            if file_path.exists():
                file_path.unlink()
                removed_files += 1

        removed_workouts = self.storage.delete_generated_workouts_after(after_date_str)
        removed_prework = self.storage.delete_prework_future(after_date_str)

        cutoff_version = version_for_day(after_date)
        future_versions = [version for version in self.storage.list_schedule_versions() if version > cutoff_version]
        removed_versions = self.storage.delete_schedule_versions(future_versions)

        return {
            "generated_workouts": removed_workouts,
            "generated_files": removed_files,
            "prework_assignments": removed_prework["assignments"],
            "prework_assignment_status": removed_prework["assignment_status"],
            "prework_logs": removed_prework["logs"],
            "schedule_versions": removed_versions,
        }


def _mark_first_pending_prework_assignment(
    storage: Storage,
    pending_rows: list[Any],
    date_str: str,
    exercise: str,
    outcome: str,
    source_text: str,
) -> None:
    for row in pending_rows:
        if row["date"] == date_str and row["exercise"] == exercise:
            storage.mark_prework_assignment(date_str, int(row["slot"]), outcome, source_text)
            pending_rows.remove(row)
            break


def _current_prework_targets(progress: dict[str, dict[str, int]]) -> dict[str, int]:
    return {exercise: values["current_target"] for exercise, values in progress.items()}


def _schedule_has_missing_details(structure: dict[str, Any]) -> bool:
    return any(not day.get("details") for day in structure.values())


def _assignment_target(assignment: Any, progress: dict[str, dict[str, int]]) -> int | None:
    exercise = str(assignment["exercise"])
    if exercise == "break":
        return None
    target = assignment["target"]
    if target is not None:
        return int(target)
    return progress[exercise]["current_target"]


def _normalize_feedback_value(value: str, allowed_values: set[str], field_name: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in allowed_values:
        allowed_text = ", ".join(sorted(item for item in allowed_values if item))
        raise ValueError(f"Invalid {field_name} feedback '{value}'. Use one of: {allowed_text}.")
    return normalized


def _format_feedback_memory(source_text: str, completion: str, difficulty: str, enjoyment: str) -> str:
    details = []
    if completion:
        details.append(f"completion={completion}")
    if difficulty:
        details.append(f"difficulty={difficulty}")
    if enjoyment:
        details.append(f"enjoyment={enjoyment}")
    if details:
        return f"{source_text} ({', '.join(details)})"
    return source_text


def _memory_source_date(start_date: date | None, end_date: date | None) -> str | None:
    if start_date is None and end_date is None:
        return None
    if start_date is not None and end_date is not None:
        if start_date == end_date:
            return start_date.isoformat()
        return f"{start_date.isoformat()} to {end_date.isoformat()}"
    if start_date is not None:
        return start_date.isoformat()
    return end_date.isoformat() if end_date is not None else None


def _summarize_app_request_safely(request_text: str) -> str:
    try:
        summary = summarize_app_request(request_text).strip()
    except Exception:
        return "Summary unavailable; use the raw request."
    return summary or "Summary unavailable; use the raw request."


def _format_app_request_document(created_at: str, summary: str, request_text: str) -> str:
    return "\n".join(
        [
            "---",
            "status: new",
            f"created_at: {created_at}",
            "source: workout-generator-settings",
            "---",
            "",
            "# App Change Request",
            "",
            "## Summary For Agent",
            summary,
            "",
            "## Raw Request",
            _markdown_fence(request_text),
            "",
            "## Handling Notes",
            "- Discuss the request with the user before implementing when scope or intent is ambiguous.",
            "- After the request is implemented or explicitly declined, delete this file so the inbox only contains open work.",
            "",
        ]
    )


def _markdown_fence(text: str) -> str:
    longest_backtick_run = max((len(match.group(0)) for match in re.finditer(r"`{3,}", text)), default=2)
    fence = "`" * (longest_backtick_run + 1)
    return f"{fence}text\n{text}\n{fence}"


def _write_agent_update_readme(root: Path) -> None:
    readme_path = root / "README.md"
    if readme_path.exists():
        return
    readme_path.write_text(
        "# Agent Updates\n\n"
        "This hidden directory is written by the Workout Generator settings page.\n\n"
        "When the user asks an advanced coding agent to look for updates, inspect "
        "`requests/*.md` for files with `status: new`, discuss the requested changes "
        "with the user, implement the agreed work, and then delete handled request files "
        "so the directory only contains open work.\n"
    )
