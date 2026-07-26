"""Flask web interface for the workout generator."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import os
import sys
from typing import Any

from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.serving import make_server

from workout_generator.app import WorkoutApp
from workout_generator.markdown import render_workout_markdown, workout_focus_label


SCHEDULE_RADIUS_DAYS = 3
TOMORROW_DEFAULT_HOUR = 18


def create_app(workout_app: WorkoutApp | None = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("WORKOUT_WEB_SECRET", "workout-generator-local")
    app.config["WORKOUT_APP"] = workout_app or WorkoutApp()
    app.jinja_env.filters["workout_markdown"] = render_workout_markdown
    app.jinja_env.filters["workout_focus"] = workout_focus_label
    app.jinja_env.filters["timestamp"] = _format_timestamp

    @app.context_processor
    def inject_theme() -> dict[str, str]:
        return {"theme": _service(app).get_theme()}

    @app.get("/")
    def index() -> str:
        service = _service(app)
        today = date.today()
        default_date = _default_selected_date()
        selected_date = _parse_request_date("date", default_date)
        schedule_start = selected_date - timedelta(days=SCHEDULE_RADIUS_DAYS)
        schedule_end = selected_date + timedelta(days=SCHEDULE_RADIUS_DAYS)

        schedule_window = service.get_schedule_window(schedule_start, SCHEDULE_RADIUS_DAYS * 2 + 1)
        schedule_day = service.get_schedule_day(selected_date)
        saved_workout = service.get_saved_workout(selected_date)
        saved_workouts = {
            day.date.isoformat(): service.get_saved_workout(day.date)
            for day in schedule_window
        }
        workout_questions = service.list_workout_questions(selected_date)
        revision_thread = service.get_workout_revision_thread(selected_date)

        return render_template(
            "workout_generator/index.html",
            today=today,
            selected_date=selected_date,
            tomorrow=today + timedelta(days=1),
            yesterday=today - timedelta(days=1),
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            schedule_window=schedule_window,
            schedule_day=schedule_day,
            saved_workout=saved_workout,
            saved_workouts=saved_workouts,
            workout_questions=workout_questions,
            revision_thread=revision_thread,
            previous_date=selected_date - timedelta(days=1),
            next_date=selected_date + timedelta(days=1),
        )

    @app.get("/daily-reps")
    def daily_reps() -> str:
        service = _service(app)
        today = date.today()
        selected_date = _parse_request_date("date", _default_selected_date())
        prework_plan = service.get_prework_plan(selected_date)
        due_items = service.get_due_prework_items(selected_date)
        progress = service.get_prework_progress()
        history = service.get_prework_history(limit=8)

        return render_template(
            "workout_generator/primer.html",
            today=today,
            selected_date=selected_date,
            tomorrow=today + timedelta(days=1),
            yesterday=today - timedelta(days=1),
            previous_date=selected_date - timedelta(days=1),
            next_date=selected_date + timedelta(days=1),
            prework_plan=prework_plan,
            due_items=due_items,
            progress=progress,
            history=history,
        )

    @app.get("/ratings")
    def ratings() -> str:
        service = _service(app)
        today = date.today()
        selected_date = _parse_request_date("date", _default_selected_date())
        return render_template(
            "workout_generator/ratings.html",
            today=today,
            selected_date=selected_date,
            previous_date=selected_date - timedelta(days=1),
            next_date=selected_date + timedelta(days=1),
            feedback_entries=service.list_feedback_for_date(selected_date),
        )

    @app.get("/primer")
    def primer_redirect() -> Any:
        return redirect(url_for("daily_reps", **dict(request.args)))

    @app.get("/prework")
    def prework_redirect() -> Any:
        return redirect(url_for("daily_reps", **dict(request.args)))

    @app.get("/settings")
    def settings() -> str:
        service = _service(app)
        selected_date = _parse_request_date("date", _default_selected_date())
        return render_template(
            "workout_generator/settings.html",
            selected_date=selected_date,
            preferences=service.list_preferences(),
            coaching_memory=service.list_coaching_memory(),
            progress=service.get_prework_progress(),
            ntfy_server=service.get_ntfy_server(),
            ntfy_topic=service.get_ntfy_topic(),
        )

    @app.post("/workout")
    def workout() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", date.today())
        note = request.form.get("note", "")
        action = request.form.get("action", "generate")
        try:
            previous = service.get_saved_workout(selected_date)
            if action == "revise":
                raise ValueError("Use the Revision Discussion before applying changes.")
            else:
                if previous is not None:
                    flash("Saved workout already exists. Use Revise to change it.", "warning")
                else:
                    service.get_or_create_workout(selected_date, note=note)
                    flash("Workout generated.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")

        return redirect(_day_url(selected_date, "workout"))

    @app.post("/workout-revision")
    def workout_revision() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.discuss_workout_revision(selected_date, request.form.get("message", ""))
            flash("Revision discussion updated. The workout has not changed.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")
        return redirect(_day_url(selected_date, "revision-discussion"))

    @app.post("/apply-workout-revision")
    def apply_workout_revision() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.apply_workout_revision(selected_date, message=request.form.get("message", ""))
            flash("Revision applied to the saved workout.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")
        return redirect(_day_url(selected_date, "workout"))

    @app.post("/discard-workout-revision")
    def discard_workout_revision() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.discard_workout_revision(selected_date)
            flash("Revision discussion discarded. The workout was not changed.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(_day_url(selected_date, "revision-discussion"))

    @app.post("/workout-question")
    def workout_question() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        question = request.form.get("question", "")
        thread_id = None
        saved_id = None
        try:
            thread_id = _parse_optional_positive_int("thread_id")
            answer = service.answer_workout_question(selected_date, question, thread_id=thread_id)
            saved_id = service.save_workout_question(
                selected_date,
                question,
                answer,
                thread_id=thread_id,
            )
            flash("Reply added." if thread_id is not None else "Question answered.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")

        fragment_id = thread_id or saved_id
        fragment = f"thread-{fragment_id}" if fragment_id else "workout-question"
        return redirect(_day_url(selected_date, fragment))

    @app.post("/send-workout")
    def send_workout() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            message_count = service.send_workout_to_phone(selected_date)
            suffix = "" if message_count == 1 else f" in {message_count} parts"
            flash(f"Formatted workout sent to your phone{suffix}.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")
        return redirect(_day_url(selected_date, "workout"))

    @app.post("/phone-settings")
    def phone_settings() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.set_ntfy_topic(request.form.get("topic", ""))
            flash("Phone delivery topic saved. Subscribe to this exact topic in ntfy.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("settings", date=selected_date.isoformat()))

    @app.post("/phone-test")
    def phone_test() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.send_phone_test()
            flash("Test notification sent. Check your phone.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("settings", date=selected_date.isoformat()))

    @app.post("/appearance")
    def appearance() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.set_theme(request.form.get("theme", "light"))
            flash("Appearance saved.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("settings", date=selected_date.isoformat()))

    @app.post("/app-request")
    def app_request() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", _default_selected_date())
        try:
            service.save_app_request(request.form.get("text", ""))
            flash("App request saved.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("settings", date=selected_date.isoformat()))

    @app.post("/pre-log")
    def pre_log() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", date.today())
        outcome = request.form.get("outcome", "")

        try:
            if outcome not in {"done", "missed", "failed", "skipped"}:
                raise ValueError("Daily Reps outcome must be done, did not do, failed, or skipped.")
            due_by_key = {
                (item.date.isoformat(), item.slot): item
                for item in service.get_due_prework_items(selected_date)
            }
            items = [
                due_by_key[key]
                for key in (_parse_selection(token) for token in request.form.getlist("selected"))
                if key in due_by_key
            ]
            if not items:
                raise ValueError("Select at least one due Daily Reps item.")
            for item in items:
                service.log_prework_assignment(item, outcome, source_text="web")
            noun = "item" if len(items) == 1 else "items"
            verb = "Skipped" if outcome == "skipped" else "Logged"
            flash(f"{verb} {len(items)} Daily Reps {noun}.", "success")
        except ValueError as exc:
            flash(str(exc), "error")

        return redirect(url_for("daily_reps", date=selected_date.isoformat()))

    @app.post("/preference")
    def preference() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", date.today())
        text = request.form.get("text", "").strip()
        if not text:
            flash("Preference text is required.", "error")
        else:
            service.save_preference(text)
            flash("Preference saved.", "success")
        return redirect(url_for("settings", date=selected_date.isoformat()))

    @app.post("/feedback")
    def feedback() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", date.today())
        text = request.form.get("text", "").strip()
        completion = request.form.get("completion", "")
        difficulty = request.form.get("difficulty", "")
        enjoyment = request.form.get("enjoyment", "")
        remember = request.form.get("remember") == "1"
        try:
            record = service.record_feedback(
                text,
                completion=completion,
                difficulty=difficulty,
                enjoyment=enjoyment,
                target_date=selected_date,
                remember=remember,
            )
            flash("Feedback stored and remembered." if record.remembered else "Feedback stored.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("ratings", date=selected_date.isoformat()))

    @app.post("/clear")
    def clear() -> Any:
        service = _service(app)
        selected_date = _parse_form_date("date", date.today())
        after_date = _parse_form_date("after", selected_date)
        results = service.clear_future(after_date)
        total_removed = sum(results.values())
        flash(f"Cleared future state after {after_date.isoformat()} ({total_removed} rows/files removed).", "success")
        return redirect(url_for("settings", date=after_date.isoformat()))

    @app.get("/healthz")
    def healthz() -> tuple[str, int]:
        return "ok", 200

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the workout generator web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="0", help="Port number, or 'random' for any free local port")
    args = parser.parse_args(argv)

    port = _parse_port(args.port)
    app = create_app()
    server = make_server(args.host, port, app, threaded=True)
    actual_port = int(server.socket.getsockname()[1])
    display_host = "localhost" if args.host in {"127.0.0.1", "0.0.0.0", "::"} else args.host
    print(f"Workout web app running at http://{display_host}:{actual_port}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 0
    return 0


def _service(app: Flask) -> WorkoutApp:
    return app.config["WORKOUT_APP"]


def _day_url(selected_date: date, fragment: str | None = None) -> str:
    target_url = url_for("index", date=selected_date.isoformat())
    if fragment:
        return f"{target_url}#{fragment}"
    return target_url


def _default_selected_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    if current.hour >= TOMORROW_DEFAULT_HOUR:
        return current.date() + timedelta(days=1)
    return current.date()


def _format_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    formatted = parsed.strftime("%b %d, %Y at %I:%M %p")
    return formatted.replace(" 0", " ").replace("at 0", "at ")


def _parse_request_date(name: str, default: date) -> date:
    raw_value = request.args.get(name, "")
    try:
        return _parse_date_value(raw_value, default)
    except ValueError as exc:
        flash(str(exc), "error")
        return default


def _parse_form_date(name: str, default: date) -> date:
    try:
        return _parse_date_value(request.form.get(name, ""), default)
    except ValueError as exc:
        flash(str(exc), "error")
        return default


def _parse_date_value(raw_value: str | None, default: date) -> date:
    value = (raw_value or "").strip()
    if not value:
        return default

    today = date.today()
    shortcuts = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
    }
    lowered = value.lower()
    if lowered in shortcuts:
        return shortcuts[lowered]

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc


def _parse_optional_positive_int(name: str) -> int | None:
    raw_value = request.form.get(name, "").strip()
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive.")
    return value


def _parse_port(raw_value: str) -> int:
    value = raw_value.strip().lower()
    if value in {"", "0", "auto", "random"}:
        return 0
    try:
        port = int(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid port '{raw_value}'. Use a number or 'random'.") from exc
    if port < 0 or port > 65535:
        raise SystemExit("Port must be between 0 and 65535.")
    return port


def _parse_selection(token: str) -> tuple[str, int] | None:
    date_part, separator, slot_part = token.partition("|")
    if not separator:
        return None
    try:
        return date_part, int(slot_part)
    except ValueError:
        return None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
