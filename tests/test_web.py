from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
import unittest.mock

import numpy as np

from workout_generator.app import WorkoutApp
from workout_generator.storage import Storage
from workout_generator.web import create_app


_MOCK_WORKOUT = (
    "# Workout for 2026-04-20\n"
    "- Schedule type: `run`\n"
    "- Request note: Keep it short\n\n"
    "## Focus\nMock focus.\n\n"
    "## Session\nMock session.\n\n"
    "## Notes\n- Mock note.\n"
)


class WorkoutWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.storage = Storage(root / "workout.sqlite3")
        self.workout_app = WorkoutApp(
            storage=self.storage,
            generated_workout_root=root / "generated",
            app_request_root=root / ".agent_updates",
            np_random=np.random.RandomState(0),
        )
        flask_app = create_app(self.workout_app)
        flask_app.config["TESTING"] = True
        self.client = flask_app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_index_renders_day_view_without_dashboard_clutter(self) -> None:
        response = self.client.get("/?date=2026-04-20")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Schedule", body)
        self.assertIn("Daily Reps", body)
        self.assertIn("Workout", body)
        self.assertIn("2026-04-20", body)
        self.assertNotIn("No details", body)
        self.assertNotIn("No schedule details", body)
        self.assertNotIn("Force regenerate", body)
        self.assertNotIn("Manual log", body)
        self.assertNotIn('class="day-link-detail"', body)

    def test_schedule_centers_three_days_around_selection_and_moves_one_day(self) -> None:
        response = self.client.get("/?date=2026-04-20")

        body = response.data.decode()
        self.assertEqual(body.count('class="day-link '), 7)
        self.assertIn("2026-04-17 through 2026-04-23", body)
        self.assertIn("/?date=2026-04-19", body)
        self.assertIn("/?date=2026-04-21", body)
        self.assertNotIn("2026-04-16", body)
        self.assertNotIn("2026-04-24", body)

    def test_workout_post_generates_and_displays_saved_workout(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            response = self.client.post(
                "/workout",
                data={"date": "2026-04-20", "note": "Keep it short", "action": "generate"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Workout generated.", body)
        self.assertIn("Mock session.", body)
        self.assertIsNotNone(self.storage.get_generated_workout("2026-04-20"))

    def test_saved_workout_auto_displays_on_get(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            self.workout_app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")

        response = self.client.get("/?date=2026-04-20")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Mock session.", body)
        self.assertIn("<h1>Workout for 2026-04-20</h1>", body)
        self.assertNotIn("# Workout for 2026-04-20", body)
        self.assertNotIn("Schedule type:", body)
        self.assertNotIn("Request note:", body)
        self.assertIn("Saved", body)
        self.assertIn('class="day-link-detail">Mock focus.</span>', body)

    def test_workout_generation_errors_are_shown_in_browser(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.generate_workout_markdown",
            side_effect=RuntimeError("GEMINI_API_KEY is not set."),
        ):
            response = self.client.post(
                "/workout",
                data={"date": "2026-04-20", "note": "", "action": "generate"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("GEMINI_API_KEY is not set.", response.data.decode())

    def test_due_prework_item_can_be_logged(self) -> None:
        through_date = date(2026, 4, 20)
        for day in [date(2026, 4, 17), date(2026, 4, 18), date(2026, 4, 19), through_date]:
            self.workout_app.get_prework_plan(day)
        due_item = self.workout_app.get_due_prework_items(through_date)[0]

        response = self.client.post(
            "/pre-log",
            data={
                "date": through_date.isoformat(),
                "selected": f"{due_item.date.isoformat()}|{due_item.slot}",
                "outcome": "done",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Logged 1 Daily Reps item.", response.data.decode())
        remaining = self.workout_app.get_due_prework_items(through_date)
        self.assertTrue(all(not (item.date == due_item.date and item.slot == due_item.slot) for item in remaining))

    def test_daily_reps_page_supports_failed_attempt(self) -> None:
        target = date(2026, 4, 20)
        due_item = None
        for offset in range(7):
            candidate = date(2026, 4, 20 + offset)
            self.workout_app.get_prework_plan(candidate)
            due_items = self.workout_app.get_due_prework_items(candidate)
            if due_items:
                target = candidate
                due_item = due_items[0]
                break
        self.assertIsNotNone(due_item)

        response = self.client.post(
            "/pre-log",
            data={
                "date": target.isoformat(),
                "selected": f"{due_item.date.isoformat()}|{due_item.slot}",
                "outcome": "failed",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Logged 1 Daily Reps item.", response.data.decode())
        self.assertIn("Failed", response.data.decode())
        progress = self.storage.get_prework_progress()
        self.assertEqual(progress[due_item.exercise]["current_target"], due_item.target)
        self.assertEqual(progress[due_item.exercise]["streak"], -1)

    def test_daily_reps_page_supports_did_not_do(self) -> None:
        target = date(2026, 4, 20)
        due_item = None
        for offset in range(7):
            candidate = date(2026, 4, 20 + offset)
            self.workout_app.get_prework_plan(candidate)
            due_items = self.workout_app.get_due_prework_items(candidate)
            if due_items:
                target = candidate
                due_item = due_items[0]
                break
        self.assertIsNotNone(due_item)

        response = self.client.post(
            "/pre-log",
            data={
                "date": target.isoformat(),
                "selected": f"{due_item.date.isoformat()}|{due_item.slot}",
                "outcome": "missed",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Logged 1 Daily Reps item.", response.data.decode())
        self.assertIn("Missed", response.data.decode())
        progress = self.storage.get_prework_progress()
        self.assertEqual(progress[due_item.exercise]["current_target"], due_item.target - 1)

    def test_daily_reps_page_logs_all_selected_items_at_once(self) -> None:
        through_date = date(2026, 4, 28)
        for offset in range(14):
            self.workout_app.get_prework_plan(date(2026, 4, 15) + timedelta(days=offset))
        due_items = self.workout_app.get_due_prework_items(through_date)
        self.assertGreater(len(due_items), 1)

        response = self.client.post(
            "/pre-log",
            data={
                "date": through_date.isoformat(),
                "selected": [f"{item.date.isoformat()}|{item.slot}" for item in due_items],
                "outcome": "skipped",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"Skipped {len(due_items)} Daily Reps items.", response.data.decode())
        self.assertEqual(self.workout_app.get_due_prework_items(through_date), [])
        self.assertEqual(self.storage.list_prework_logs(limit=10), [])

    def test_feedback_post_accepts_quick_ratings_without_text(self) -> None:
        response = self.client.post(
            "/feedback",
            data={
                "date": "2026-04-20",
                "completion": "completed",
                "difficulty": "hard",
                "enjoyment": "liked",
                "text": "",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Feedback stored.", response.data.decode())
        self.assertIn("Ratings and Notes", response.data.decode())
        self.assertIn('<a href="/ratings?date=2026-04-20" class="active">Ratings</a>', response.data.decode())
        feedback = self.storage.list_feedback_entries()
        self.assertEqual(feedback[0]["date_start"], "2026-04-20")
        self.assertEqual(feedback[0]["completion"], "completed")
        self.assertEqual(feedback[0]["difficulty"], "hard")
        self.assertEqual(feedback[0]["enjoyment"], "liked")

    def test_feedback_post_can_remember_note_for_future_workouts(self) -> None:
        response = self.client.post(
            "/feedback",
            data={
                "date": "2026-04-20",
                "completion": "completed",
                "difficulty": "hard",
                "enjoyment": "",
                "text": "Heavy squats were fine, but high-rep lunges annoyed my knee.",
                "remember": "1",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Feedback stored and remembered.", response.data.decode())
        memory = self.storage.list_coaching_memory_entries()
        self.assertEqual(memory[0]["source_date"], "2026-04-20")
        self.assertIn("high-rep lunges annoyed my knee", memory[0]["content"])

    def test_ratings_is_a_separate_selected_day_page(self) -> None:
        day_response = self.client.get("/?date=2026-04-20")
        ratings_response = self.client.get("/ratings?date=2026-04-20")

        self.assertNotIn("Save day note", day_response.data.decode())
        self.assertIn("Save day note", ratings_response.data.decode())
        self.assertIn("Monday, April 20, 2026", ratings_response.data.decode())

    def test_workout_question_does_not_regenerate_saved_workout(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            original = self.workout_app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")

        with (
            unittest.mock.patch("workout_generator.app.generate_workout_markdown") as generate_mock,
            unittest.mock.patch(
                "workout_generator.app.generate_workout_answer",
                return_value="Drop the load enough to keep two clean reps in reserve. The listed weight is only a starting point.",
            ) as answer_mock,
        ):
            response = self.client.post(
                "/workout-question",
                data={"date": "2026-04-20", "question": "What if the weight is too heavy?"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Question answered.", response.data.decode())
        self.assertIn("Drop the load enough", response.data.decode())
        self.assertIn('class="comment-time"', response.data.decode())
        self.assertEqual(self.workout_app.get_saved_workout(date(2026, 4, 20)).content, original.content)
        generate_mock.assert_not_called()
        answer_mock.assert_called_once()

    def test_workout_question_supports_threaded_replies(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            self.workout_app.get_or_create_workout(date(2026, 4, 20))
        with unittest.mock.patch(
            "workout_generator.app.generate_workout_answer",
            return_value="Yes, keep the same effort target.",
        ):
            self.client.post(
                "/workout-question",
                data={"date": "2026-04-20", "question": "Can I use a trap bar?"},
            )
        root_id = self.workout_app.list_workout_questions(date(2026, 4, 20))[0]["id"]

        with unittest.mock.patch(
            "workout_generator.app.generate_workout_answer",
            return_value="Use the high handles first.",
        ) as answer_mock:
            response = self.client.post(
                "/workout-question",
                data={
                    "date": "2026-04-20",
                    "thread_id": str(root_id),
                    "question": "Which handles?",
                },
                follow_redirects=True,
            )

        body = response.data.decode()
        self.assertIn("Reply added.", body)
        self.assertIn("Can I use a trap bar?", body)
        self.assertIn("Which handles?", body)
        self.assertIn("Use the high handles first.", body)
        self.assertIn("Reply in this thread", body)
        self.assertEqual(answer_mock.call_args.kwargs["prior_questions"][0]["id"], root_id)

    def test_revision_discussion_does_not_change_workout_until_apply(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            original = self.workout_app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")

        with unittest.mock.patch(
            "workout_generator.app.generate_revision_discussion",
            return_value="I will only shorten the cooldown; everything else remains unchanged.",
        ):
            discussion_response = self.client.post(
                "/workout-revision",
                data={"date": "2026-04-20", "message": "Only shorten the cooldown."},
                follow_redirects=True,
            )

        discussion_body = discussion_response.data.decode()
        self.assertIn("Revision discussion updated. The workout has not changed.", discussion_body)
        self.assertIn("Apply revision", discussion_body)
        self.assertIn("Workout Questions", discussion_body)
        self.assertIn('class="comment-time"', discussion_body)
        self.assertEqual(self.workout_app.get_saved_workout(date(2026, 4, 20)).content, original.content)

        revised_content = _MOCK_WORKOUT.replace("Mock session.", "Cooldown shortened only.")
        with unittest.mock.patch(
            "workout_generator.app.revise_workout_markdown",
            return_value=revised_content,
        ) as revise_mock:
            apply_response = self.client.post(
                "/apply-workout-revision",
                data={"date": "2026-04-20"},
                follow_redirects=True,
            )

        self.assertIn("Revision applied to the saved workout.", apply_response.data.decode())
        self.assertIn("Cooldown shortened only.", self.workout_app.get_saved_workout(date(2026, 4, 20)).content)
        self.assertEqual(revise_mock.call_args.args[0], original.content)

    def test_apply_revision_incorporates_typed_message(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            original = self.workout_app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")

        revised_content = _MOCK_WORKOUT.replace("Mock session.", "Bike intervals instead.")
        with unittest.mock.patch(
            "workout_generator.app.revise_workout_markdown",
            return_value=revised_content,
        ) as revise_mock:
            response = self.client.post(
                "/apply-workout-revision",
                data={"date": "2026-04-20", "message": "Swap the run for a bike, my shin hurts."},
                follow_redirects=True,
            )

        self.assertIn("Revision applied to the saved workout.", response.data.decode())
        saved = self.workout_app.get_saved_workout(date(2026, 4, 20))
        self.assertIn("Bike intervals instead.", saved.content)
        self.assertNotEqual(saved.content, original.content)
        self.assertEqual(
            revise_mock.call_args.kwargs["final_instruction"],
            "Swap the run for a bike, my shin hurts.",
        )

    def test_revision_apply_button_shares_the_discussion_form(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            self.workout_app.get_or_create_workout(date(2026, 4, 20), note="Keep it short")

        body = self.client.get("/?date=2026-04-20").data.decode()
        # Apply is a submit button on the discussion form (formaction), so the text in
        # the message box is posted with it instead of being dropped by a separate form.
        self.assertIn('name="message"', body)
        self.assertIn('formaction="/apply-workout-revision"', body)

    def test_workout_question_provider_errors_are_shown_in_browser(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            self.workout_app.get_or_create_workout(date(2026, 4, 20))

        with unittest.mock.patch(
            "workout_generator.app.generate_workout_answer",
            side_effect=RuntimeError("GEMINI_API_KEY is not set."),
        ):
            response = self.client.post(
                "/workout-question",
                data={"date": "2026-04-20", "question": "How hard should this feel?"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("GEMINI_API_KEY is not set.", response.data.decode())

    def test_settings_page_holds_profile_and_state(self) -> None:
        response = self.client.get("/settings?date=2026-04-20")

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("Appearance", body)
        self.assertIn("Preferences", body)
        self.assertIn("Coach Memory", body)
        self.assertIn("Daily Reps Targets", body)
        self.assertIn("Phone Delivery", body)
        self.assertIn("App Requests", body)
        self.assertIn("https://ntfy.sh", body)
        self.assertIn("workout-", body)

    def test_appearance_post_persists_dark_mode(self) -> None:
        response = self.client.post(
            "/appearance",
            data={"date": "2026-04-20", "theme": "dark"},
            follow_redirects=True,
        )

        body = response.data.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("Appearance saved.", body)
        self.assertIn('data-theme="dark"', body)
        self.assertIn('<option value="dark" selected>Dark</option>', body)
        self.assertEqual(self.workout_app.get_theme(), "dark")

    def test_app_request_post_saves_request_without_showing_agent_details(self) -> None:
        with unittest.mock.patch(
            "workout_generator.app.summarize_app_request",
            return_value="- Save app change requests for a coding agent.",
        ):
            response = self.client.post(
                "/app-request",
                data={"date": "2026-04-20", "text": "Make the workout page easier to scan."},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        body = response.data.decode()
        self.assertIn("App request saved.", body)
        self.assertIn("Requested change", body)
        request_files = list((self.workout_app.app_request_root / "requests").glob("*.md"))
        self.assertEqual(len(request_files), 1)
        self.assertIn("Make the workout page easier to scan.", request_files[0].read_text())

    def test_send_workout_posts_formatted_html_to_phone(self) -> None:
        with unittest.mock.patch("workout_generator.app.generate_workout_markdown", return_value=_MOCK_WORKOUT):
            self.workout_app.get_or_create_workout(date(2026, 4, 20))

        with unittest.mock.patch("workout_generator.app.publish_html_attachment", return_value=1) as publish_mock:
            response = self.client.post(
                "/send-workout",
                data={"date": "2026-04-20"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Formatted workout sent to your phone.", response.data.decode())
        publish_mock.assert_called_once()

    def test_phone_test_sends_setup_notification(self) -> None:
        with unittest.mock.patch("workout_generator.app.publish_markdown", return_value=1) as publish_mock:
            response = self.client.post(
                "/phone-test",
                data={"date": "2026-04-20"},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Test notification sent. Check your phone.", response.data.decode())
        publish_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
