from __future__ import annotations

import unittest
import unittest.mock

from workout_generator.notifications import publish_html_attachment, publish_markdown, split_markdown


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class NotificationTests(unittest.TestCase):
    def test_split_markdown_keeps_each_message_under_limit(self) -> None:
        markdown = "# Workout\n\n" + "- exercise target\n" * 20

        chunks = split_markdown(markdown, max_bytes=80)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 80 for chunk in chunks))
        self.assertEqual("\n".join(chunks).split(), markdown.split())

    def test_publish_markdown_uses_rendered_markdown_and_private_topic(self) -> None:
        with unittest.mock.patch(
            "workout_generator.notifications.urlopen",
            return_value=_Response(),
        ) as urlopen_mock:
            count = publish_markdown(
                topic="workout-private_topic",
                markdown="# Workout\n\n- Run 5 km",
                title="Workout for 2026-06-21",
            )

        self.assertEqual(count, 1)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.full_url, "https://ntfy.sh/workout-private_topic")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Content-type"], "text/plain; charset=utf-8")
        self.assertEqual(request.headers["Markdown"], "yes")
        self.assertEqual(request.headers["Title"], "Workout for 2026-06-21")
        self.assertEqual(request.headers["Click"], "https://ntfy.sh/workout-private_topic")
        self.assertEqual(
            request.headers["Actions"],
            "view, Open formatted workout, https://ntfy.sh/workout-private_topic",
        )
        self.assertIn(b"Run 5 km", request.data)

    def test_publish_html_attachment_sends_a_tappable_workout_file(self) -> None:
        with unittest.mock.patch(
            "workout_generator.notifications.urlopen",
            return_value=_Response(),
        ) as urlopen_mock:
            count = publish_html_attachment(
                topic="workout-private_topic",
                html="<!doctype html><h1>Workout</h1>",
                title="Workout for 2026-06-21",
                filename="workout-2026-06-21.html",
            )

        self.assertEqual(count, 1)
        request = urlopen_mock.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.headers["Content-type"], "text/html; charset=utf-8")
        self.assertEqual(request.headers["Filename"], "workout-2026-06-21.html")
        self.assertIn(b"<h1>Workout</h1>", request.data)


if __name__ == "__main__":
    unittest.main()
