from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from workout_generator.generator import (
    _QUESTION_SYSTEM_INSTRUCTION,
    _REVISION_APPLY_SYSTEM_INSTRUCTION,
    _REVISION_DISCUSSION_SYSTEM_INSTRUCTION,
    _SYSTEM_INSTRUCTION,
    _build_question_message,
    _build_revision_apply_message,
    _build_revision_discussion_message,
    _build_user_message,
    _format_coaching_memory,
    _read_user_profile,
)
from workout_generator.models import ScheduleDay
from workout_generator.storage import Storage


class WorkoutGeneratorContextTests(unittest.TestCase):
    def test_read_user_profile_includes_nested_user_info_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            profile_root = Path(temp_name)
            (profile_root / "README.md").write_text("ignore this")
            (profile_root / "preferences.md").write_text("top-level preference")
            user_info = profile_root / "user_info"
            user_info.mkdir()
            (user_info / "info.md").write_text("run-biased variety")
            (user_info / "gym_situation.md").write_text("Default Eagle gym")

            profile_text = _read_user_profile(profile_root)

        self.assertIn("### preferences.md", profile_text)
        self.assertIn("top-level preference", profile_text)
        self.assertIn("### user_info/gym_situation.md", profile_text)
        self.assertIn("Default Eagle gym", profile_text)
        self.assertIn("### user_info/info.md", profile_text)
        self.assertIn("run-biased variety", profile_text)
        self.assertNotIn("ignore this", profile_text)

    def test_system_instruction_contains_coaching_context_rules(self) -> None:
        self.assertIn("Default gym: Eagle", _SYSTEM_INSTRUCTION)
        self.assertIn("Cardio days are run-biased with variety", _SYSTEM_INSTRUCTION)
        self.assertIn("strength plus variety", _SYSTEM_INSTRUCTION)
        self.assertIn("Use custom workouts as inspiration", _SYSTEM_INSTRUCTION)
        self.assertIn("Act as a coach trying to move the user to the next level", _SYSTEM_INSTRUCTION)
        self.assertIn("not templates to copy", _SYSTEM_INSTRUCTION)
        self.assertIn("Do not copy the frequency, split, exercise counts, or distribution", _SYSTEM_INSTRUCTION)
        self.assertIn("Run or cardio days may include a short strength", _SYSTEM_INSTRUCTION)
        self.assertIn("Gym days may include short cardio or conditioning", _SYSTEM_INSTRUCTION)
        self.assertIn("mixed work should be occasional", _SYSTEM_INSTRUCTION)
        self.assertIn("The schedule type is the primary focus", _SYSTEM_INSTRUCTION)
        self.assertIn("Treat completion, difficulty, enjoyment, and freeform feedback", _SYSTEM_INSTRUCTION)
        self.assertIn("Do not ignore relevant feedback or durable coaching memory", _SYSTEM_INSTRUCTION)
        self.assertIn("## Warmup", _SYSTEM_INSTRUCTION)
        self.assertIn("## Accessories / Conditioning", _SYSTEM_INSTRUCTION)
        self.assertNotIn("- Schedule type: `{type}`", _SYSTEM_INSTRUCTION)
        self.assertNotIn("- Schedule details: {details}", _SYSTEM_INSTRUCTION)

    def test_build_user_message_ignores_random_schedule_subtype_hints(self) -> None:
        day = ScheduleDay(
            date=date(2026, 4, 20),
            type="gym",
            details=["random subtype hint that should not steer generation"],
        )

        message = _build_user_message(day, note="", storage=None)

        self.assertIn("**Schedule type:** gym", message)
        self.assertNotIn("random subtype hint that should not steer generation", message)

    def test_build_user_message_includes_optional_feedback_ratings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            storage = Storage(Path(temp_name) / "workout.sqlite3")
            storage.initialize()
            storage.add_feedback(
                source_text="2026-04-18 bench day felt good",
                date_start="2026-04-18",
                date_end="2026-04-18",
                completion="completed",
                difficulty="hard",
                enjoyment="liked",
            )
            day = ScheduleDay(date=date(2026, 4, 20), type="gym", details=[])

            message = _build_user_message(day, note="", storage=storage)

        self.assertIn("2026-04-18 bench day felt good", message)
        self.assertIn("completion: completed", message)
        self.assertIn("difficulty: hard", message)
        self.assertIn("enjoyment: liked", message)

    def test_build_user_message_includes_durable_coaching_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            storage = Storage(Path(temp_name) / "workout.sqlite3")
            storage.initialize()
            storage.add_coaching_memory(
                content="Low back felt better when deadlifts stayed at RPE 7.",
                source_type="feedback",
                source_date="2026-04-18",
            )
            day = ScheduleDay(date=date(2026, 4, 20), type="gym", details=[])

            message = _build_user_message(day, note="", storage=storage)

        self.assertIn("--- DURABLE COACHING MEMORY ---", message)
        self.assertIn(
            "feedback | 2026-04-18: Low back felt better when deadlifts stayed at RPE 7.",
            message,
        )

    def test_coaching_memory_context_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            storage = Storage(Path(temp_name) / "workout.sqlite3")
            storage.initialize()
            for index in range(45):
                storage.add_coaching_memory(
                    content=f"Remembered training context {index}",
                    source_type="feedback",
                    source_date=f"2026-04-{index + 1:02d}",
                )

            memory = _format_coaching_memory(storage)

        self.assertIn("older coaching memory entries omitted", memory)
        self.assertNotIn("Remembered training context 0", memory)
        self.assertIn("Remembered training context 44", memory)

    def test_build_user_message_includes_only_previous_saved_workouts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            storage = Storage(Path(temp_name) / "workout.sqlite3")
            storage.initialize()
            storage.save_generated_workout(
                date_str="2026-04-19",
                schedule_type="off",
                schedule_details=[],
                note="rest day",
                content="# Off day\nRecovery walk only",
                file_path="/tmp/off.md",
            )
            storage.save_generated_workout(
                date_str="2026-04-18",
                schedule_type="gym",
                schedule_details=[],
                note="previous day",
                content="# Previous workout\nDeadlifts and rows",
                file_path="/tmp/previous.md",
            )
            storage.save_generated_workout(
                date_str="2026-04-20",
                schedule_type="run",
                schedule_details=[],
                note="same day",
                content="# Current workout\nShould not be prior context",
                file_path="/tmp/current.md",
            )
            storage.save_generated_workout(
                date_str="2026-04-21",
                schedule_type="gym",
                schedule_details=[],
                note="future day",
                content="# Future workout\nShould not be prior context",
                file_path="/tmp/future.md",
            )
            day = ScheduleDay(date=date(2026, 4, 20), type="run", details=[])

            message = _build_user_message(day, note="", storage=storage)

        self.assertIn("RECENT PREVIOUS WORKOUTS", message)
        self.assertIn("Date: 2026-04-18", message)
        self.assertIn("Deadlifts and rows", message)
        self.assertNotIn("Recovery walk only", message)
        self.assertNotIn("Date: 2026-04-19", message)
        self.assertNotIn("Should not be prior context", message)
        self.assertNotIn("Date: 2026-04-21", message)

    def test_question_message_includes_workout_profile_and_conversation(self) -> None:
        message = _build_question_message(
            workout_content="# Workout\nDeadlift: 3 x 5 at 225 lb",
            question="What should the deadlifts feel like?",
            prior_questions=[
                {
                    "question": "How long will this take?",
                    "answer": "About 50 minutes.",
                }
            ],
        )

        self.assertIn("Deadlift: 3 x 5 at 225 lb", message)
        self.assertIn("USER PROFILE:", message)
        self.assertIn("User: How long will this take?", message)
        self.assertIn("Coach: About 50 minutes.", message)
        self.assertIn("CURRENT QUESTION:\nWhat should the deadlifts feel like?", message)

    def test_question_instruction_requests_a_direct_natural_answer(self) -> None:
        self.assertIn("natural, conversational voice", _QUESTION_SYSTEM_INSTRUCTION)
        self.assertIn("do not rewrite the workout", _QUESTION_SYSTEM_INSTRUCTION)
        self.assertIn("without headings or markdown", _QUESTION_SYSTEM_INSTRUCTION)

    def test_revision_discussion_uses_original_and_does_not_apply_changes(self) -> None:
        message = _build_revision_discussion_message(
            "# Workout\nOriginal deadlift session",
            "Only shorten the cooldown",
            [{"user_text": "Keep the lifts", "assistant_text": "The lifts will remain unchanged."}],
        )

        self.assertIn("Original deadlift session", message)
        self.assertIn("User: Keep the lifts", message)
        self.assertIn("CURRENT MESSAGE:\nOnly shorten the cooldown", message)
        self.assertIn("Do not rewrite the workout yet", _REVISION_DISCUSSION_SYSTEM_INSTRUCTION)

    def test_revision_apply_requires_minimal_edits_to_original(self) -> None:
        message = _build_revision_apply_message(
            "# Workout\nOriginal deadlift session",
            [{"user_text": "Shorten cooldown", "assistant_text": "Only the cooldown will change."}],
        )

        self.assertIn("ORIGINAL SAVED WORKOUT", message)
        self.assertIn("Only the cooldown will change", message)
        self.assertIn("Preserve every exercise", _REVISION_APPLY_SYSTEM_INSTRUCTION)
        self.assertIn("smallest edit", _REVISION_APPLY_SYSTEM_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
