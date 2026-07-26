"""Safe Markdown rendering for saved workout content."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markupsafe import Markup, escape


_RENDERER = MarkdownIt("commonmark", {"html": False, "linkify": False})
_HIDDEN_METADATA_PREFIXES = ("- Schedule type:", "- Schedule details:", "- Request note:")


def render_markdown(content: str) -> Markup:
    """Render model-authored Markdown while escaping embedded HTML."""
    return Markup(_RENDERER.render(content))


def render_workout_markdown(content: str) -> Markup:
    """Render a workout without legacy schedule metadata lines."""
    return render_markdown(clean_workout_markdown(content))


def clean_workout_markdown(content: str) -> str:
    """Remove legacy metadata that should not appear in saved workout content."""
    return "\n".join(
        line for line in content.splitlines() if not line.startswith(_HIDDEN_METADATA_PREFIXES)
    )


def workout_focus_label(content: str, max_length: int = 110) -> str:
    """Return a compact label from a generated workout's Focus section.

    Schedule subtype hints are planning metadata and can be stale or misleading.
    The generated workout's own focus is the useful description to show in the
    schedule rail.
    """

    in_focus = False
    for raw_line in clean_workout_markdown(content).splitlines():
        line = raw_line.strip()
        if line.lower() == "## focus":
            in_focus = True
            continue
        if in_focus and line.startswith("#"):
            break
        if not in_focus or not line:
            continue

        label = re.sub(r"[*_`~]", "", line)
        label = re.sub(r"\s+", " ", label).strip(" -")
        if not label:
            continue
        if len(label) > max_length:
            return label[: max_length - 1].rstrip() + "…"
        return label

    return "Generated"


def render_workout_document(content: str, title: str, request_note: str = "") -> str:
    """Build a standalone mobile HTML document for phone delivery."""
    note_html = ""
    if request_note.strip():
        note_html = f'<aside class="request"><strong>Request:</strong> {escape(request_note.strip())}</aside>'
    workout_html = render_workout_markdown(content)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ margin: 0; background: #f4f6f3; color: #17211b; font: 17px/1.55 system-ui, sans-serif; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 24px 18px 48px; }}
    article {{ padding: 22px; border: 1px solid #d9dfd8; border-radius: 10px; background: white; }}
    h1 {{ margin: 0 0 18px; font-size: 1.6rem; }}
    h2 {{ margin: 24px 0 9px; padding-top: 15px; border-top: 1px solid #d9dfd8; color: #184d40; font-size: 1.15rem; }}
    h3 {{ margin: 18px 0 7px; font-size: 1rem; }}
    p, ul, ol {{ margin: 0 0 14px; }}
    ul, ol {{ padding-left: 25px; }}
    li + li {{ margin-top: 6px; }}
    code {{ padding: 2px 5px; border-radius: 4px; background: #eef3f0; font-size: .9em; }}
    .request {{ margin-bottom: 16px; padding: 12px 14px; border-radius: 7px; background: #eef3f0; }}
  </style>
</head>
<body>
  <main>
    {note_html}
    <article>{workout_html}</article>
  </main>
</body>
</html>"""
