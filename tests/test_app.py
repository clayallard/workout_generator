from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest
import unittest.mock

import numpy as np

from workout_generator.app import WorkoutApp
from workout_generator.storage import Storage

_MOCK_WORKOUT = (
    "# Workout for 2026-04-20\n"
    "- Schedule type: `run`\n"
    "- Request note: I have been traveling and only have 30 minutes\n\n"
    "## Focus\nMock focus.\n\n"
    "## Session\nMock session.\n\n"
    "## Notes\n- Mock note.\n"
)


class WorkoutAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.generated_root = root / "generated"
        self.storage = Storage(root / "workout.sqlite3")
        self.app = WorkoutApp(
            storage=self.storage,
            generated_workout_root=self.generated_root,
            app_request_root=root / ".agent_updates",
            np_random=np.random.RandomState(0),
        )
        self._gen_patcher = unittest.mock.patch(
            "workout_generator.app.generate_workout_markdown",
            return_value=_MOCK_WORKOUT,
        )
        self._gen_patcher.start()

    def tearDown(self) -> None:
        self._gen_patcher.stop()
        self.temp_dir.cleanup()

    def test_get_prework_plan_persists_assignments(self) -> None:
        first = self.app.get_prework_plan(date(2026, 4, 20))
        second = self.app.get_prework_plan(date(2026, 4, 20))

        self.assertEqual(first.slots, second.slots)
        self.assertEqual(len(first.slots), 2)

    def test_get_schedule_day_repairs_saved_schedule_without_details(self) -> None:
        self.storage.save_schedule_structure(
            "2026-1",
            {
                str(index): {"type": "run" if index % 2 == 0 else "gym", "details": []}
                for index in range(14)
            },
        )

        day = self.app.get_schedule_day(date(2026, 4, 20))
        repaired = self.storage.get_schedule_structure("2026-1")

        self.assertTrue(day.details)
        self.assertTrue(all(repaired[str(index)]["details"] for index in range(14)))

    def test_prework_plan_preserves_target_snapshot_when_reopened(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.generate_daily_assignments",
            return_value=["push ups", "break"],
        ):
            first = self.app.get_prework_plan(date(2026, 4, 20))

        self.storage.set_prework_progress("push ups", 80, 0)
        second = self.app.get_prework_plan(date(2026, 4, 20))

        self.assertEqual(first.slots[0].target, 65)
        self.assertEqual(second.slots[0].target, 65)
        self.assertEqual(second.slots[0].exercise, "push ups")

    def test_due_prework_uses_target_snapshot_for_backlog(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.generate_daily_assignments",
            return_value=["push ups", "break"],
        ):
            self.app.get_prework_plan(date(2026, 4, 20))

        self.storage.set_prework_progress("push ups", 80, 0)
        due_items = self.app.get_due_prework_items(date(2026, 4, 20))

        self.assertEqual(due_items[0].target, 65)

    def test_prework_assignment_history_records_logged_target_snapshot(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.generate_daily_assignments",
            return_value=["push ups", "break"],
        ):
            self.app.get_prework_plan(date(2026, 4, 20))
        due_item = self.app.get_due_prework_items(date(2026, 4, 20))[0]
        self.storage.set_prework_progress("push ups", 80, 0)

        self.app.log_prework_assignment(due_item, "done", source_text="test")

        history = self.storage.list_prework_logs(limit=10)
        self.assertEqual(history[0]["target"], "65")
        self.assertEqual(history[0]["exercise"], "push ups")

    def test_log_prework_updates_progress(self) -> None:
        self.app.log_prework(date(2026, 4, 20), done=["push ups"], missed=["squats"])
        progress = self.storage.get_prework_progress()

        self.assertEqual(progress["push ups"]["current_target"], 65)
        self.assertEqual(progress["push ups"]["streak"], 1)
        self.assertEqual(progress["squats"]["current_target"], 51)
        self.assertEqual(progress["squats"]["streak"], 0)

    def test_failed_prework_attempt_lowers_target_after_two_in_a_row(self) -> None:
        self.app.log_prework(date(2026, 4, 20), failed=["push ups"])
        first_progress = self.storage.get_prework_progress()
        self.app.log_prework(date(2026, 4, 21), failed=["push ups"])
        second_progress = self.storage.get_prework_progress()

        self.assertEqual(first_progress["push ups"]["current_target"], 65)
        self.assertEqual(first_progress["push ups"]["streak"], -1)
        self.assertEqual(second_progress["push ups"]["current_target"], 64)
        self.assertEqual(second_progress["push ups"]["streak"], 0)

    def test_skipped_prework_does_not_change_progression(self) -> None:
        self.app.log_prework(date(2026, 4, 20), skipped=["push ups"])
        progress = self.storage.get_prework_progress()

        self.assertEqual(progress["push ups"]["current_target"], 65)
        self.assertEqual(progress["push ups"]["streak"], 0)
        self.assertEqual(self.storage.list_prework_logs(limit=10), [])

    def test_get_or_create_workout_writes_markdown_file(self) -> None:
        workout = self.app.get_or_create_workout(
            date(2026, 4, 20),
            note="I have been traveling and only have 30 minutes",
        )

        self.assertTrue(workout.file_path.exists())
        self.assertIn("Workout for 2026-04-20", workout.content)
        self.assertIn("Request note", workout.content)
        self.assertIn("30 minutes", workout.content)

    def test_non_revise_request_keeps_saved_workout(self) -> None:
        original = self.app.get_or_create_workout(
            date(2026, 4, 20),
            note="I have been traveling and only have 30 minutes",
        )
        repeated = self.app.get_or_create_workout(date(2026, 4, 20), note="")

        self.assertEqual(repeated.content, original.content)
        self.assertEqual(repeated.note, original.note)

    def test_revise_workout_replaces_saved_workout(self) -> None:
        self.app.get_or_create_workout(
            date(2026, 4, 20),
            note="I have been traveling and only have 30 minutes",
        )
        revised_content = _MOCK_WORKOUT.replace("Mock session.", "Shortened session.")
        with unittest.mock.patch(
            "workout_generator.app.revise_workout_markdown",
            return_value=revised_content,
        ) as revise_mock:
            revised = self.app.revise_workout(date(2026, 4, 20), "Make this shorter")

        self.assertEqual(revised.note, "I have been traveling and only have 30 minutes")
        self.assertIn("Shortened session.", revised.content)
        revise_mock.assert_called_once()
        self.assertEqual(revise_mock.call_args.args[0], _MOCK_WORKOUT)

    def test_revision_discussion_preserves_workout_until_explicit_apply(self) -> None:
        original = self.app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")
        with unittest.mock.patch(
            "workout_generator.app.generate_revision_discussion",
            return_value="Understood. I will keep everything unchanged and only record your acknowledgment.",
        ) as discuss_mock:
            thread = self.app.discuss_workout_revision(
                date(2026, 4, 20),
                "Keep everything the same; just acknowledge this request.",
            )

        self.assertEqual(self.app.get_saved_workout(date(2026, 4, 20)).content, original.content)
        self.assertEqual(thread["status"], "active")
        self.assertEqual(len(thread["messages"]), 1)
        self.assertEqual(discuss_mock.call_args.kwargs["workout_content"], original.content)

        revised_content = original.content.replace("Mock session.", "Confirmed session.")
        with unittest.mock.patch(
            "workout_generator.app.revise_workout_markdown",
            return_value=revised_content,
        ) as revise_mock:
            revised = self.app.apply_workout_revision(date(2026, 4, 20))

        self.assertIn("Confirmed session.", revised.content)
        self.assertEqual(revise_mock.call_args.args[0], original.content)
        self.assertEqual(
            revise_mock.call_args.args[1][0]["user_text"],
            "Keep everything the same; just acknowledge this request.",
        )
        self.assertEqual(self.app.get_workout_revision_thread(date(2026, 4, 20))["status"], "applied")

    def test_apply_workout_revision_uses_typed_instruction_without_discussion(self) -> None:
        original = self.app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")
        revised_content = original.content.replace("Mock session.", "Knee-safe session.")
        with unittest.mock.patch(
            "workout_generator.app.revise_workout_markdown",
            return_value=revised_content,
        ) as revise_mock:
            revised = self.app.apply_workout_revision(
                date(2026, 4, 20),
                message="Drop the lunges, my knee hurts, and pick a safe replacement.",
            )

        self.assertIn("Knee-safe session.", revised.content)
        self.assertEqual(revise_mock.call_args.args[0], original.content)
        self.assertEqual(revise_mock.call_args.args[1], [])
        self.assertEqual(
            revise_mock.call_args.kwargs["final_instruction"],
            "Drop the lunges, my knee hurts, and pick a safe replacement.",
        )
        thread = self.app.get_workout_revision_thread(date(2026, 4, 20))
        self.assertEqual(thread["status"], "applied")
        self.assertEqual(
            thread["messages"][-1]["user_text"],
            "Drop the lunges, my knee hurts, and pick a safe replacement.",
        )
        self.assertEqual(self.app.get_saved_workout(date(2026, 4, 20)).content, revised.content)

    def test_apply_workout_revision_forwards_discussion_and_typed_instruction(self) -> None:
        self.app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")
        with unittest.mock.patch(
            "workout_generator.app.generate_revision_discussion",
            return_value="What would you like to do instead of the lunges?",
        ):
            self.app.discuss_workout_revision(date(2026, 4, 20), "I can't do lunges, my knee hurts.")

        revised_content = _MOCK_WORKOUT.replace("Mock session.", "Step-ups instead of lunges.")
        with unittest.mock.patch(
            "workout_generator.app.revise_workout_markdown",
            return_value=revised_content,
        ) as revise_mock:
            self.app.apply_workout_revision(date(2026, 4, 20), message="You decide.")

        passed_messages = revise_mock.call_args.args[1]
        self.assertEqual(passed_messages[0]["user_text"], "I can't do lunges, my knee hurts.")
        self.assertEqual(revise_mock.call_args.kwargs["final_instruction"], "You decide.")
        self.assertIn(
            "Step-ups instead of lunges.",
            self.app.get_saved_workout(date(2026, 4, 20)).content,
        )

    def test_apply_workout_revision_without_thread_or_message_is_rejected(self) -> None:
        self.app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")
        with self.assertRaises(ValueError):
            self.app.apply_workout_revision(date(2026, 4, 20))

    def test_due_prework_items_only_include_due_assignments(self) -> None:
        through_date = date(2026, 4, 19)
        candidate_dates = [date(2026, 4, 17), date(2026, 4, 18), date(2026, 4, 19), date(2026, 4, 20)]
        for candidate in candidate_dates:
            self.app.get_prework_plan(candidate)

        due_items = self.app.get_due_prework_items(through_date)

        self.assertTrue(all(item.date <= through_date for item in due_items))
        self.assertTrue(all(item.exercise in {"push ups", "sit ups", "squats"} for item in due_items))

    def test_log_prework_assignment_marks_item_complete(self) -> None:
        candidate_dates = [date(2026, 4, 17), date(2026, 4, 18), date(2026, 4, 19)]
        for candidate in candidate_dates:
            self.app.get_prework_plan(candidate)
        due_items = self.app.get_due_prework_items(date(2026, 4, 19))
        self.assertTrue(due_items)
        due_item = due_items[0]

        self.app.log_prework_assignment(due_item, "done", source_text="test")

        remaining = self.app.get_due_prework_items(date(2026, 4, 19))
        self.assertTrue(all(not (item.date == due_item.date and item.slot == due_item.slot) for item in remaining))

    def test_skipped_prework_assignment_is_removed_without_history_or_progress_change(self) -> None:
        for candidate in [date(2026, 4, 17), date(2026, 4, 18), date(2026, 4, 19)]:
            self.app.get_prework_plan(candidate)
        due_item = self.app.get_due_prework_items(date(2026, 4, 19))[0]
        progress_before = self.storage.get_prework_progress()

        self.app.log_prework_assignment(due_item, "skipped", source_text="test")

        remaining = self.app.get_due_prework_items(date(2026, 4, 19))
        self.assertTrue(all(not (item.date == due_item.date and item.slot == due_item.slot) for item in remaining))
        self.assertEqual(self.storage.list_prework_logs(limit=10), [])
        self.assertEqual(self.storage.get_prework_progress(), progress_before)

    def test_clear_generated_daily_reps_preserves_logs_and_progress(self) -> None:
        due_item = None
        for offset in range(7):
            candidate = date(2026, 4, 20 + offset)
            self.app.get_prework_plan(candidate)
            due_items = self.app.get_due_prework_items(candidate)
            if due_items:
                due_item = due_items[0]
                break
        self.assertIsNotNone(due_item)

        self.app.log_prework_assignment(due_item, "done", source_text="test")
        progress_before = self.storage.get_prework_progress()

        results = self.app.clear_generated_daily_reps()

        self.assertGreaterEqual(results["assignments"], 1)
        self.assertGreaterEqual(results["assignment_status"], 1)
        self.assertEqual(self.storage.get_prework_assignments(due_item.date.isoformat()), None)
        self.assertEqual(self.storage.list_prework_logs(limit=10)[0]["outcome"], "done")
        self.assertEqual(self.storage.get_prework_progress(), progress_before)

    def test_feedback_records_date_span_when_present(self) -> None:
        record = self.app.record_feedback("2026-04-10 felt easy, 2026-04-12 felt hard")

        self.assertEqual(record.date_start, date(2026, 4, 10))
        self.assertEqual(record.date_end, date(2026, 4, 12))

    def test_feedback_records_optional_quick_ratings(self) -> None:
        record = self.app.record_feedback(
            "",
            completion="completed",
            difficulty="hard",
            enjoyment="liked",
            target_date=date(2026, 4, 20),
        )
        rows = self.storage.list_feedback_entries()

        self.assertEqual(record.date_start, date(2026, 4, 20))
        self.assertEqual(record.completion, "completed")
        self.assertEqual(record.difficulty, "hard")
        self.assertEqual(record.enjoyment, "liked")
        self.assertEqual(rows[0]["completion"], "completed")
        self.assertEqual(rows[0]["difficulty"], "hard")
        self.assertEqual(rows[0]["enjoyment"], "liked")

    def test_feedback_can_be_remembered_as_coaching_memory(self) -> None:
        record = self.app.record_feedback(
            "Knees felt beat up after downhill intervals.",
            difficulty="hard",
            target_date=date(2026, 4, 20),
            remember=True,
        )
        memory = self.storage.list_coaching_memory_entries()

        self.assertTrue(record.remembered)
        self.assertEqual(memory[0]["source_type"], "feedback")
        self.assertEqual(memory[0]["source_date"], "2026-04-20")
        self.assertIn("Knees felt beat up after downhill intervals.", memory[0]["content"])
        self.assertIn("difficulty=hard", memory[0]["content"])

    def test_workout_question_requires_saved_workout_and_persists_answer(self) -> None:
        self.app.get_or_create_workout(date(2026, 4, 20))

        with unittest.mock.patch(
            "workout_generator.app.generate_workout_answer",
            return_value="Those weights are starting targets. Lower them until the working sets match the listed effort.",
        ) as answer_mock:
            answer = self.app.answer_workout_question(date(2026, 4, 20), "What if the weight is too heavy?")
        self.app.save_workout_question(date(2026, 4, 20), "What if the weight is too heavy?", answer)
        questions = self.app.list_workout_questions(date(2026, 4, 20))

        self.assertIn("starting targets", answer)
        answer_mock.assert_called_once_with(
            workout_content=_MOCK_WORKOUT,
            question="What if the weight is too heavy?",
            prior_questions=[],
        )
        self.assertEqual(questions[0]["question"], "What if the weight is too heavy?")
        self.assertEqual(questions[0]["answer"], answer)
        self.assertEqual(questions[0]["replies"], [])

    def test_workout_question_reply_uses_only_its_thread_context(self) -> None:
        self.app.get_or_create_workout(date(2026, 4, 20))
        root_id = self.app.save_workout_question(
            date(2026, 4, 20),
            "Can I use a trap bar?",
            "Yes, use the same effort target.",
        )

        with unittest.mock.patch(
            "workout_generator.app.generate_workout_answer",
            return_value="Start with the high handles.",
        ) as answer_mock:
            answer = self.app.answer_workout_question(
                date(2026, 4, 20),
                "Which handles?",
                thread_id=root_id,
            )
        self.app.save_workout_question(
            date(2026, 4, 20),
            "Which handles?",
            answer,
            thread_id=root_id,
        )
        threads = self.app.list_workout_questions(date(2026, 4, 20))

        answer_mock.assert_called_once_with(
            workout_content=_MOCK_WORKOUT,
            question="Which handles?",
            prior_questions=[
                {
                    "id": root_id,
                    "parent_id": None,
                    "question": "Can I use a trap bar?",
                    "answer": "Yes, use the same effort target.",
                    "created_at": unittest.mock.ANY,
                }
            ],
        )
        self.assertEqual(threads[0]["replies"][0]["question"], "Which handles?")

    def test_ntfy_topic_is_private_shaped_and_persisted(self) -> None:
        first = self.app.get_ntfy_topic()
        second = self.app.get_ntfy_topic()

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("workout-"))
        self.assertGreaterEqual(len(first), 8)

    def test_send_workout_to_phone_publishes_formatted_html_attachment(self) -> None:
        self.app.get_or_create_workout(
            date(2026, 4, 20),
            note="I have been traveling and only have 30 minutes",
        )
        self.app.set_ntfy_topic("workout-private-topic")

        with unittest.mock.patch("workout_generator.app.publish_html_attachment", return_value=1) as publish_mock:
            message_count = self.app.send_workout_to_phone(date(2026, 4, 20))

        self.assertEqual(message_count, 1)
        call = publish_mock.call_args.kwargs
        self.assertEqual(call["topic"], "workout-private-topic")
        self.assertEqual(call["title"], "Workout for 2026-04-20")
        self.assertEqual(call["filename"], "workout-2026-04-20.html")
        self.assertIn("<h1>Workout for 2026-04-20</h1>", call["html"])
        self.assertNotIn("Schedule type", call["html"])
        self.assertIn("I have been traveling and only have 30 minutes", call["html"])

    def test_ntfy_topic_rejects_unsafe_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "ntfy topic"):
            self.app.set_ntfy_topic("too short!")

    def test_theme_setting_defaults_to_light_and_persists_dark(self) -> None:
        self.assertEqual(self.app.get_theme(), "light")

        self.app.set_theme("dark")

        self.assertEqual(self.app.get_theme(), "dark")
        self.assertEqual(self.storage.get_setting("theme"), "dark")
        with self.assertRaisesRegex(ValueError, "Theme"):
            self.app.set_theme("blue")

    def test_save_app_request_writes_hidden_agent_request_file(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.summarize_app_request",
            return_value="- Add a compact app request textbox.",
        ):
            file_path = self.app.save_app_request("Please add a place to save app change ideas.")

        self.assertEqual(file_path.parent, self.app.app_request_root / "requests")
        self.assertTrue(file_path.exists())
        self.assertTrue((self.app.app_request_root / "README.md").exists())
        content = file_path.read_text()
        self.assertIn("status: new", content)
        self.assertIn("Summary For Agent", content)
        self.assertIn("- Add a compact app request textbox.", content)
        self.assertIn("Please add a place to save app change ideas.", content)
        self.assertIn("delete this file", content)

    def test_save_app_request_keeps_raw_text_when_summary_is_unavailable(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.summarize_app_request",
            side_effect=RuntimeError("GEMINI_API_KEY is not set."),
        ):
            file_path = self.app.save_app_request("The settings page needs a faster request box.")

        content = file_path.read_text()
        self.assertIn("Summary unavailable; use the raw request.", content)
        self.assertIn("The settings page needs a faster request box.", content)

    def test_clear_future_removes_future_generated_state_and_future_versions(self) -> None:
        self.app.get_prework_plan(date(2026, 4, 20))
        self.app.get_prework_plan(date(2026, 5, 2))
        self.app.get_or_create_workout(date(2026, 4, 20))
        self.app.get_or_create_workout(date(2026, 5, 2))
        self.app.get_schedule_day(date(2026, 4, 29))
        self.app.get_schedule_day(date(2026, 5, 2))

        results = self.app.clear_future(date(2026, 4, 30))

        self.assertGreaterEqual(results["generated_workouts"], 1)
        self.assertGreaterEqual(results["prework_assignments"], 1)
        self.assertEqual(self.storage.get_generated_workout("2026-05-02"), None)
        self.assertTrue(self.storage.get_schedule_structure("2026-1") is not None)
        self.assertTrue(self.storage.get_schedule_structure("2026-2") is None)
