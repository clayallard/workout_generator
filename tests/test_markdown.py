from __future__ import annotations

import unittest

from workout_generator.markdown import (
    render_markdown,
    render_workout_document,
    render_workout_markdown,
    workout_focus_label,
)


class MarkdownRenderingTests(unittest.TestCase):
    def test_render_markdown_builds_workout_structure(self) -> None:
        rendered = str(render_markdown("# Workout\n\n## Main Work\n\n- Squat: **3 x 5**"))

        self.assertIn("<h1>Workout</h1>", rendered)
        self.assertIn("<h2>Main Work</h2>", rendered)
        self.assertIn("<li>Squat: <strong>3 x 5</strong></li>", rendered)

    def test_render_markdown_escapes_embedded_html(self) -> None:
        rendered = str(render_markdown("<script>alert('bad')</script>"))

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_render_workout_markdown_hides_legacy_metadata(self) -> None:
        rendered = str(
            render_workout_markdown(
                "# Workout\n- Schedule type: `gym`\n- Schedule details: gym\n"
                "- Request note: Keep it short\n\n## Focus\nStrength"
            )
        )

        self.assertNotIn("Schedule type", rendered)
        self.assertNotIn("Schedule details", rendered)
        self.assertNotIn("Request note", rendered)
        self.assertIn("<h2>Focus</h2>", rendered)

    def test_render_workout_document_includes_request_and_mobile_html(self) -> None:
        rendered = render_workout_document(
            "# Workout\n\n## Focus\nStrength",
            "Workout for 2026-06-21",
            "Keep it under an hour",
        )

        self.assertIn('<meta name="viewport"', rendered)
        self.assertIn("<h2>Focus</h2>", rendered)
        self.assertIn("<strong>Request:</strong> Keep it under an hour", rendered)

    def test_workout_focus_label_comes_from_generated_focus_section(self) -> None:
        self.assertEqual(
            workout_focus_label(
                "# Workout\n\n## Focus\n**Build an aerobic base** while keeping the effort controlled."
            ),
            "Build an aerobic base while keeping the effort controlled.",
        )

    def test_workout_focus_label_has_a_generated_fallback(self) -> None:
        self.assertEqual(workout_focus_label("# Workout\n\n## Main Work\nSquats"), "Generated")


if __name__ == "__main__":
    unittest.main()
