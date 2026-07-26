"""Command-line interface for the workout generator."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

from workout_generator.app import WorkoutApp


VALID_EXERCISES = {"push ups", "sit ups", "squats"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workout", description="Local-first workout planning and coaching")
    subparsers = parser.add_subparsers(dest="command", required=True)

    schedule_parser = subparsers.add_parser("schedule", help="Show the deterministic schedule")
    _add_date_options(schedule_parser, "start", date.today())
    schedule_parser.add_argument("--days", type=int, default=14)

    pre_parser = subparsers.add_parser("pre", help="Show the next pre-work assignments")
    _add_date_options(pre_parser, "date", date.today() + timedelta(days=1))

    pre_log_parser = subparsers.add_parser("pre-log", help="Log completed or missed pre-work")
    _add_date_options(pre_log_parser, "date", date.today())
    pre_log_parser.add_argument("--done", default="")
    pre_log_parser.add_argument("--missed", default="")

    workout_parser = subparsers.add_parser(
        "workout",
        aliases=["next"],
        help="Generate or show the saved workout for a date",
    )
    _add_date_options(workout_parser, "date", date.today())
    workout_parser.add_argument("--note", default="")
    workout_parser.add_argument("--note-file", type=Path)
    workout_parser.add_argument("--regenerate", action="store_true", help=argparse.SUPPRESS)

    revise_parser = subparsers.add_parser("revise", help="Revise a generated workout for a date")
    _add_date_options(revise_parser, "date", date.today())
    revise_parser.add_argument("--note", default="")
    revise_parser.add_argument("--note-file", type=Path)

    clear_parser = subparsers.add_parser("clear", help="Clear generated future state after a cutoff date")
    _add_date_options(clear_parser, "after", date.today())

    feedback_parser = subparsers.add_parser("feedback", help="Store retrospective workout feedback")
    feedback_parser.add_argument("--text", default="")
    feedback_parser.add_argument("--file", type=Path)
    feedback_parser.add_argument("--date", type=_parse_date)
    feedback_parser.add_argument("--completion", choices=["completed", "partial", "missed"], default="")
    feedback_parser.add_argument("--difficulty", choices=["easy", "as_expected", "hard"], default="")
    feedback_parser.add_argument("--enjoyment", choices=["liked", "neutral", "disliked"], default="")
    feedback_parser.add_argument("--remember", action="store_true", help="Keep this feedback in durable coaching memory")

    pref_parser = subparsers.add_parser("preference", help="Save a durable training preference")
    pref_parser.add_argument("--text", default="")
    pref_parser.add_argument("--list", action="store_true", dest="list_prefs")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app = WorkoutApp()

    if args.command == "schedule":
        start_date = _resolve_relative_date(args, "start", date.today())
        return _handle_schedule(app, start_date, args.days)
    if args.command == "pre":
        target_date = _resolve_relative_date(args, "date", date.today() + timedelta(days=1))
        return _handle_pre(app, target_date)
    if args.command == "pre-log":
        target_date = _resolve_relative_date(args, "date", date.today())
        return _handle_pre_log(app, target_date, args.done, args.missed)
    if args.command in {"workout", "next"}:
        target_date = _resolve_relative_date(args, "date", date.today())
        note = _load_optional_text(args.note, args.note_file)
        return _handle_workout(app, target_date, note, args.regenerate)
    if args.command == "revise":
        target_date = _resolve_relative_date(args, "date", date.today() + timedelta(days=1))
        note = _load_optional_text(args.note, args.note_file).strip()
        return _handle_revise(app, target_date, note)
    if args.command == "clear":
        after_date = _resolve_relative_date(args, "after", date.today())
        return _handle_clear(app, after_date)
    if args.command == "feedback":
        text = _load_optional_text(args.text, args.file)
        if not text.strip() and not any((args.completion, args.difficulty, args.enjoyment)):
            parser.error("feedback requires --text, --file, or at least one quick rating")
        return _handle_feedback(
            app,
            text,
            completion=args.completion,
            difficulty=args.difficulty,
            enjoyment=args.enjoyment,
            target_date=args.date,
            remember=args.remember,
        )
    if args.command == "preference":
        if args.list_prefs:
            return _handle_preference_list(app)
        if not args.text.strip():
            parser.error("preference requires --text or --list")
        return _handle_preference_save(app, args.text)

    parser.error("unknown command")
    return 2


def _handle_schedule(app: WorkoutApp, start_date: date, days: int) -> int:
    window = app.get_schedule_window(start_date, days)
    for schedule_day in window:
        print(f"{schedule_day.date.isoformat()}: {schedule_day.type}")
    return 0


def _handle_pre(app: WorkoutApp, target_date: date) -> int:
    plan = app.get_prework_plan(target_date)
    print(f"Pre-work for {plan.date.isoformat()}:")
    for slot in plan.slots:
        if slot.exercise == "break":
            print(f"- Slot {slot.slot}: break")
        else:
            print(f"- Slot {slot.slot}: {slot.target} {slot.exercise}")
    return 0


def _handle_pre_log(app: WorkoutApp, target_date: date, done_raw: str, missed_raw: str) -> int:
    done = _parse_exercise_csv(done_raw)
    missed = _parse_exercise_csv(missed_raw)
    if not done and not missed:
        return _handle_pre_log_interactive(app, target_date)
    overlap = set(done) & set(missed)
    if overlap:
        raise SystemExit(f"Exercises cannot be both done and missed: {', '.join(sorted(overlap))}")
    app.log_prework(target_date, done=done, missed=missed)
    print(f"Logged pre-work for {target_date.isoformat()}.")
    if done:
        print(f"- Done: {', '.join(done)}")
    if missed:
        print(f"- Missed: {', '.join(missed)}")
    return 0


def _handle_pre_log_interactive(app: WorkoutApp, through_date: date) -> int:
    due_items = app.get_due_prework_items(through_date)
    if not due_items:
        print(f"No unlogged pre-work assignments due on or before {through_date.isoformat()}.")
        return 0

    print(f"Logging pre-work through {through_date.isoformat()}.")
    print("Enter `y` for done, `n` for missed, `s` to skip, or `q` to quit.")
    for item in due_items:
        prompt = f"{item.date.isoformat()} slot {item.slot}: {item.target} {item.exercise}? "
        while True:
            response = input(prompt).strip().lower()
            if response == "q":
                return 0
            if response == "s":
                break
            if response == "y":
                app.log_prework_assignment(item, "done", source_text="interactive")
                break
            if response == "n":
                app.log_prework_assignment(item, "missed", source_text="interactive")
                break
            print("Use `y`, `n`, `s`, or `q`.")
    return 0


def _handle_workout(app: WorkoutApp, target_date: date, note: str, regenerate: bool) -> int:
    workout = app.get_or_create_workout(target_date, note=note, regenerate=regenerate)
    print(workout.content.rstrip())
    print()
    print(f"Saved to {workout.file_path}")
    if note.strip() and not regenerate and workout.note.strip() != note.strip():
        print("Note ignored because this date already has a saved workout. Use `revise` to change it.")
    return 0


def _handle_revise(app: WorkoutApp, target_date: date, note: str) -> int:
    if not note:
        note = input("How should this workout change? ").strip()
    if not note:
        raise SystemExit("revise requires a note or interactive input.")
    workout = app.revise_workout(target_date, note)
    print(workout.content.rstrip())
    print()
    print(f"Saved to {workout.file_path}")
    return 0


def _handle_clear(app: WorkoutApp, after_date: date) -> int:
    results = app.clear_future(after_date)
    print(f"Cleared generated state after {after_date.isoformat()}.")
    print(f"- Generated workouts removed: {results['generated_workouts']}")
    print(f"- Generated files removed: {results['generated_files']}")
    print(f"- Future pre-work assignments removed: {results['prework_assignments']}")
    print(f"- Future pre-work status rows removed: {results['prework_assignment_status']}")
    print(f"- Future pre-work logs removed: {results['prework_logs']}")
    print(f"- Future schedule versions removed: {results['schedule_versions']}")
    print("Current-version schedule structure is preserved; only fully future versions are dropped.")
    return 0


def _handle_preference_save(app: WorkoutApp, text: str) -> int:
    app.save_preference(text)
    print(f"Preference saved: {text.strip()}")
    return 0


def _handle_preference_list(app: WorkoutApp) -> int:
    prefs = app.list_preferences()
    if not prefs:
        print("No preferences saved yet.")
        return 0
    print("Saved preferences:")
    for pref in prefs:
        print(f"- {pref}")
    return 0


def _handle_feedback(
    app: WorkoutApp,
    text: str,
    completion: str = "",
    difficulty: str = "",
    enjoyment: str = "",
    target_date: date | None = None,
    remember: bool = False,
) -> int:
    record = app.record_feedback(
        text,
        completion=completion,
        difficulty=difficulty,
        enjoyment=enjoyment,
        target_date=target_date,
        remember=remember,
    )
    print("Stored feedback.")
    if record.date_start and record.date_end:
        if record.date_start == record.date_end:
            print(f"- Date: {record.date_start.isoformat()}")
        else:
            print(f"- Date span: {record.date_start.isoformat()} to {record.date_end.isoformat()}")
    else:
        print("- No explicit date found in feedback text.")
    ratings = []
    if record.completion:
        ratings.append(f"completion={record.completion}")
    if record.difficulty:
        ratings.append(f"difficulty={record.difficulty}")
    if record.enjoyment:
        ratings.append(f"enjoyment={record.enjoyment}")
    if ratings:
        print(f"- Ratings: {', '.join(ratings)}")
    if record.remembered:
        print("- Remembered for future workouts.")
    return 0


def _parse_date(value: str) -> date:
    lowered = value.strip().lower()
    today = date.today()
    shortcuts = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
    }
    if lowered in shortcuts:
        return shortcuts[lowered]
    return date.fromisoformat(value)


def _add_date_options(parser: argparse.ArgumentParser, dest: str, default: date) -> None:
    parser.add_argument(f"--{dest}", type=_parse_date, default=None)
    parser.add_argument("-td", f"--today-{dest}", action="store_true", dest=f"{dest}_today")
    parser.add_argument("-tm", f"--tomorrow-{dest}", action="store_true", dest=f"{dest}_tomorrow")
    parser.add_argument("-y", f"--yesterday-{dest}", action="store_true", dest=f"{dest}_yesterday")
    parser.set_defaults(**{f"{dest}_default": default})


def _resolve_relative_date(args: argparse.Namespace, dest: str, fallback: date) -> date:
    explicit_value = getattr(args, dest, None)
    if explicit_value is not None:
        return explicit_value

    today = date.today()
    if getattr(args, f"{dest}_today", False):
        return today
    if getattr(args, f"{dest}_tomorrow", False):
        return today + timedelta(days=1)
    if getattr(args, f"{dest}_yesterday", False):
        return today - timedelta(days=1)
    return getattr(args, f"{dest}_default", fallback)


def _load_optional_text(inline_text: str, file_path: Path | None) -> str:
    if file_path is not None:
        return file_path.read_text()
    return inline_text


def _parse_exercise_csv(raw_value: str) -> list[str]:
    if not raw_value.strip():
        return []
    values = [part.strip().lower().replace("pushups", "push ups").replace("situps", "sit ups") for part in raw_value.split(",")]
    exercises: list[str] = []
    for value in values:
        if value not in VALID_EXERCISES:
            raise SystemExit(f"Unsupported exercise '{value}'. Use: push ups, sit ups, squats.")
        exercises.append(value)
    return exercises


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
