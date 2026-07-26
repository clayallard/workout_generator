# workout_generator

`workout_generator` is a local-first workout planning and coaching app. It
combines a deterministic training schedule with small daily-reps progression,
optional Gemini-powered workout generation, and a browser interface backed by
local SQLite state.

## Motivation

The project started from a practical problem: deciding what to do at the gym or
on a cardio day is easy to postpone when there is no plan ready. I wanted a
tool that could preserve a predictable weekly structure while turning a day
into an actionable session, remember what happened, and adapt when I provide
feedback.

The local-first boundary is intentional. Training preferences, generated
workouts, feedback, and notification settings belong on the user's machine;
the public repository contains the application and its tests, not a personal
training history. A fresh checkout works without a personal profile and can be
used for schedule and Daily Reps features before an AI key or profile is added.

## Features and scope

- deterministic `run`, `gym`, `off`, and combined-day scheduling
- Daily Reps assignments with completion, failure, and miss progression
- explicit CLI commands for planning, generation, revision, feedback, and cleanup
- Flask UI for the same workflow, plus saved-workout questions and revision discussions
- SQLite persistence and Markdown snapshots under a local runtime directory
- optional ntfy delivery for formatted workout notifications

This is a personal, local application rather than a hosted fitness service. It
does not provide accounts, authentication, multi-user isolation, or a
production deployment configuration. It is not medical advice; generated
workouts should be reviewed and adjusted for the user's situation.

## Reproduce the public checkout

Requirements:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

Clone the repository, install the locked dependencies, and run the tests:

```bash
git clone <your-workout-generator-repository-url>
cd workout_generator
uv sync
uv run pytest
```

The deterministic parts do not need an API key or any private files. The first
CLI command creates local runtime state under `data/`, which is intentionally
ignored by Git.

```bash
uv run workout schedule --start 2026-04-20 --days 14
uv run workout pre --date tomorrow
uv run workout pre-log --date today --done "push ups" --missed "squats"
```

## Optional personal configuration

The app reads Markdown files below `user_profile/` as local coaching context.
That directory is intentionally ignored except for its public usage guide,
[`user_profile/README.md`](./user_profile/README.md). The app also works when
the directory is empty, so a public clone never needs the author's training
details to run.

To use a personal profile locally, create one or more Markdown files under
`user_profile/` after cloning. Keep names, locations, health information,
equipment details, and other identifying material there only if you are
comfortable with the way the AI features use it. Do not force-add those files
to a public repository.

Workout generation, saved-workout Q&A, and revision discussions use Gemini. Set
the key in the shell or another local secret store; never place a real key in a
README, source file, commit, or `.env` file that will be published.

```bash
export GEMINI_API_KEY="<your-key>"
uv run workout workout --date tomorrow --note "Keep this session under one hour"
```

When an AI feature is used, the app sends the request together with the local
profile and relevant saved workout context to the configured Gemini service.
That boundary is important when deciding what to put in local profile and
feedback files.

## CLI workflow

Use the installed project command with `uv run workout` (or
`python -m workout_generator`):

| Command | Purpose |
| --- | --- |
| `schedule` | Show the deterministic schedule for a date range |
| `pre` | Show Daily Reps assignments for a date |
| `pre-log` | Record completed, failed, missed, or skipped Daily Reps |
| `workout` | Generate or show the saved workout for a date |
| `revise` | Discuss and apply a revision to a generated workout |
| `feedback` | Store retrospective feedback and optional ratings |
| `preference` | Save or list durable training preferences |
| `clear` | Remove generated future state after a cutoff date |

Examples:

```bash
uv run workout pre -tm
uv run workout pre-log -td
uv run workout workout -tm
uv run workout revise --date 2026-04-20 --note "Make this shorter"
uv run workout feedback --text "2026-04-20 felt easy" --remember
uv run workout preference --text "Prefer variety while keeping one or two strength anchors"
uv run workout clear -td
```

Date-driven commands accept `today`, `tomorrow`, and `yesterday`, as well as
the short forms `-td`, `-tm`, and `-y`.

## Web app

Start the local Flask app with an automatically selected port:

```bash
uv run workout-web --port random
```

The server prints a `http://localhost:<port>` URL. Use a fixed port when
needed:

```bash
uv run workout-web --port 5000
```

The browser workflow includes a selected-day workout view, a seven-day schedule
rail, Daily Reps logging, rendered Markdown workouts, workout generation and
revision, threaded Q&A, feedback and ratings, preferences, theme selection,
and optional ntfy delivery. If `GEMINI_API_KEY` is missing, the server still
starts and the AI actions report the missing configuration in the UI.

The app intentionally binds to localhost. GitHub Pages and GitLab Pages cannot
run this Flask/SQLite/server-side application; exposing it on a public host
would require authentication, secret management, and a deliberate data/privacy
design.

## Architecture

```text
workout_generator/schedule.py       deterministic schedule generation
workout_generator/preworkout.py     Daily Reps assignment and progression rules
workout_generator/generator.py      Gemini integration and prompt boundaries
workout_generator/storage.py        SQLite state and migrations
workout_generator/app.py            application service used by CLI and web
workout_generator/web.py            Flask routes and browser entry point
tests/                              unit and web behavior tests
```

Runtime state is created in `data/` and is never required in source control.
Older local `context/` notes and runtime history are also excluded from the
public checkout; they are development context, not application dependencies.

## License

No license has been selected for this project yet. Add one before inviting
others to reuse the code if that matches your publishing intent.
