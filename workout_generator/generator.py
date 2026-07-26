"""AI-backed workout generation and coaching using Gemini."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from workout_generator.models import ScheduleDay
from workout_generator.paths import PROJECT_ROOT

_USER_PROFILE_DIR = PROJECT_ROOT / "user_profile"
_COACHING_MEMORY_MAX_ENTRIES = 40
_COACHING_MEMORY_MAX_CHARS = 6000

_SYSTEM_INSTRUCTION = """\
You are a personal fitness coach generating a daily workout plan.

RULES:
- Respond with ONLY valid markdown. No explanations, no preamble, no apologies before or after.
- The user's note takes highest priority. If it contradicts the schedule, honor the note.
- Generate workouts appropriate for the schedule type. An "off" day means recovery, not training.
- Workouts must be safe. Modify aggressively for injury, fatigue, travel, or equipment constraints.
- Be specific: name exercises, give sets/reps or durations, provide real structure.
- Vary workouts over time — use recent workout history to avoid repeating the same session.
- Do not invent constraints not mentioned by the user.
- Treat USER PROFILE as read-only source material. The user owns those files; never ask to edit them.
- Use the user's scattered notes as calibration and inspiration, not as literal instructions to repeat blindly.
- Act as a coach trying to move the user to the next level. Prior workouts, old random systems,
  and pasted custom workouts are context for ability, preferences, and equipment fit, not templates to copy.
- Optimize each workout for the user's current goal, recent training, recovery, feedback, constraints,
  and equipment. Do not copy the frequency, split, exercise counts, or distribution of example workouts
  just because those examples appear in the profile.
- Use controlled variety. When several sensible choices fit the training goal, pick one that improves
  the overall week and recent pattern; do not add novelty or randomness that undermines progression,
  recovery, or safety.
- Preserve the schedule type and order exactly. You may only choose the workout content inside that schedule.
- The schedule type is the primary focus. A secondary block must stay brief and supportive; never let
  optional crossover work turn a run day into a gym day or a gym day into a cardio day.

USER TRAINING CONTEXT:
- Default goal: get stronger and maintain physique without a narrow competition target.
- Default gym: Eagle, with squat racks, bench stations, deadlift platforms, pull-up bars, machines, cardio machines, stretch room, and basketball court.
- If the note mentions Gaffney, use the same broad barbell/cardio equipment assumptions as Eagle.
- If the note mentions work gym, hotel-style, travel, or limited equipment, use dumbbells, one rack, treadmills, row/ski, and basic machines.
- Assume no standing injury or physical limitation unless the note says otherwise.
- Cardio days are run-biased with variety. If recent cardio was not a run, bias toward running unless the note asks for another modality.
- Cardio can use outdoor 5k-style runs, longer/shorter runs, intervals, bike, row, ski, stairs, Jacobs Ladder, or 100 made basketball threes.
- Gym days should usually use strength plus variety: 1-2 primary lifts, suggested exact weights that can be adjusted, RPE/RIR cues, accessories, core, and occasional WOD-style conditioning.
- Run or cardio days may include a short strength, prehab, mobility, or core dose only when it has a
  concrete benefit for that day's run and recovery. Gym days may include short cardio or conditioning
  when it is low-fatigue and supports the broader week. Omit crossover work when it is not useful;
  mixed work should be occasional, never a default on every day.
- Use the old max/rep tables as load calibration. Suggested weights are approximate starting targets, not obligations.
- Use custom workouts as inspiration for variants, not as a fixed 6-day split.
- Treat completion, difficulty, enjoyment, and freeform feedback as behavior-changing coaching
  signals. Use them to adjust volume, intensity, exercise selection, and recovery bias while keeping
  the user's explicit note highest priority.
- Do not ignore relevant feedback or durable coaching memory. If a remembered note or recent feedback
  item applies to today's training, adapt the workout around it. If it does not apply, briefly say why
  in Notes instead of silently discarding it.
- Combined days (`run/gym` or `gym/run`) should follow the schedule order and can be a full 1.5-2 hour session unless the note gives a shorter time limit.
- Default cardio warmup: quad stretches, kicks, thigh turns, and ankle rolls.
- Default lifting warmup: child pose, kneeling lunge rotation, arm circles, 25 push ups, 25 squats, 25 sit ups, and 12 burpees. Scale it down if the note says short, tired, injured, or limited.

SCHEDULE TYPES:
- off: rest and recovery day
- run: aerobic or running session
- gym: strength and conditioning session
- run/gym: run first, then gym work
- gym/run: gym work first, then run

REQUIRED OUTPUT FORMAT — return exactly this structure, fill in the content:

# Workout for {date}

## Focus
<one or two sentences on the primary goal of this session>

## Warmup
<specific warmup for today's schedule, scaled to the note>

## Main Work
<primary run/lift/conditioning work with exact suggested weights, sets, reps, durations, or distances>

## Accessories / Conditioning
<secondary work, core, machine work, WOD-style block, or "None" if not appropriate>

## Cooldown
<short cooldown or recovery>

## Substitutions
<equipment, crowding, time, and modality substitutions>

## Notes
<detected constraints, coaching reminders, and how feedback/profile context shaped the plan. Do not repeat schedule type or schedule details.>\
"""

_QUESTION_SYSTEM_INSTRUCTION = """\
You are the user's personal fitness coach answering a question about an already-generated workout.

Answer the question directly in a natural, conversational voice. Ground your answer in the saved
workout and the user's training profile. Be concise but specific; most answers should be one to three
short paragraphs. Refer to the actual exercises, loads, durations, or substitutions in the workout
when they matter. Use prior questions to understand follow-ups, but answer only the current question.
If the available context does not support a confident answer, say what is uncertain instead of making
up workout details.

The question is informational: do not rewrite the workout, claim that you changed it, or append a
status message about regeneration. If the user asks for a change, explain what you recommend and
briefly tell them to use Revise if they want that change saved. Do not mention prompts, supplied
context, or these instructions. Use plain text, without headings or markdown formatting.

Prioritize safe advice. Do not diagnose injuries. If the user describes sharp pain, chest pain,
dizziness, loss of function, or another potentially serious symptom, tell them to stop the relevant
activity and seek appropriate medical help.\
"""

_REVISION_DISCUSSION_SYSTEM_INSTRUCTION = """\
You are discussing a possible revision to an already-saved workout. Do not rewrite the workout yet.

Respond naturally and concisely. Confirm exactly what the user wants changed and explicitly state what
will remain unchanged. When the user states a constraint (such as an injury, missing equipment, or a
time limit) without spelling out the exact fix, do not ask them what to do instead — decide as their
coach, propose a specific and safe substitution, and tell them it will be applied when they apply the
revision. Ask a clarifying question only when the request is genuinely ambiguous and you cannot make a
safe assumption. If the user only wants acknowledgment and no workout change, acknowledge that and
clearly say the saved workout should remain unchanged. Never output a complete workout or claim that a
revision has already occurred. The user will explicitly apply the revision later.\
"""

_REVISION_APPLY_SYSTEM_INSTRUCTION = """\
You are editing an existing saved workout after the user chose to apply a revision.

Return only the complete revised workout in valid Markdown. Use the original workout as the source of
truth. Preserve every exercise, load, set, rep, duration, section, and coaching detail unless the
revision discussion or the final instruction changes it. Make the smallest edit that satisfies the
request; do not regenerate or redesign unaffected portions. Do not include schedule type, schedule
details, or a request-note metadata block. Keep the existing workout title and overall section
structure whenever possible.

The user has already chosen to apply, so you must produce a concrete revised workout now. The
discussion may state a constraint (such as an injury, missing equipment, or a time limit) without
spelling out the exact replacement, and it may end on an open coach question the user never answered.
In that case, act as the coach and decide yourself: substitute or adjust the affected work with
specific exercises, loads, and volume that respect the constraint and keep the session coherent. Never
leave the workout unchanged only because the user did not dictate the exact fix, and never ask a
question or request confirmation in your output.\
"""

_APP_REQUEST_SUMMARY_SYSTEM_INSTRUCTION = """\
You are summarizing an in-app product or engineering change request for a stronger coding agent.

Return concise Markdown bullets only. Preserve the user's intent, concrete desired behavior, important
constraints, and any uncertainty. Do not claim the work is done. Do not propose implementation details
unless the user explicitly requested one.\
"""


def _read_user_profile(profile_dir: Path = _USER_PROFILE_DIR) -> str:
    parts = []
    for path in sorted(profile_dir.rglob("*.md")):
        if path.name == "README.md":
            continue
        relative_path = path.relative_to(profile_dir).as_posix()
        parts.append(f"### {relative_path}\n\n{path.read_text()}")
    if not parts:
        return "(No user profile files found. Generate based on schedule type and context only.)"
    return "\n\n".join(parts)


def _build_user_message(day: ScheduleDay, note: str, storage) -> str:
    lines = [
        "Today's workout request:",
        "",
        f"**Date:** {day.date.isoformat()}",
        f"**Schedule type:** {day.type}",
        f"**User note:** {note.strip() or 'none'}",
        "",
        "USER PROFILE:",
        _read_user_profile(),
        "",
        "--- DURABLE COACHING MEMORY ---",
        _format_coaching_memory(storage),
        "",
        "--- RECENT PREVIOUS WORKOUTS (last 5 before requested date) ---",
    ]

    if storage is not None:
        recent = storage.list_recent_generated_workouts(limit=5, before_date_str=day.date.isoformat())
        if recent:
            for row in recent:
                snippet = str(row["content"])[:400]
                if len(str(row["content"])) > 400:
                    snippet += "..."
                lines.append(
                    f"Date: {row['date']} | Type: {row['schedule_type']} | Note: {row['note'] or 'none'}\n{snippet}"
                )
        else:
            lines.append("No previous workouts.")
    else:
        lines.append("Not available.")

    lines += ["", "--- RECENT FEEDBACK (last 30 days) ---"]
    if storage is not None:
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        feedback = storage.list_feedback_entries(after_date_str=cutoff)
        if feedback:
            for row in feedback:
                date_range = ""
                if row["date_start"] or row["date_end"]:
                    date_range = f" [{row['date_start']} to {row['date_end']}]"
                details = []
                for field in ("completion", "difficulty", "enjoyment"):
                    value = row[field]
                    if value:
                        details.append(f"{field}: {value}")
                detail_text = f" ({', '.join(details)})" if details else ""
                lines.append(f"- {row['source_text']}{date_range}{detail_text}")
        else:
            lines.append("No recent feedback.")
    else:
        lines.append("Not available.")

    lines += ["", "--- PREWORK PROGRESS ---"]
    if storage is not None:
        progress = storage.get_prework_progress()
        for exercise, values in progress.items():
            lines.append(f"- {exercise}: {values['current_target']} reps target, streak {values['streak']}")
    else:
        lines.append("Not available.")

    lines += ["", "Generate the workout now."]
    return "\n".join(lines)


def _format_coaching_memory(storage) -> str:
    if storage is None:
        return "Not available."
    entries = storage.list_coaching_memory_entries()
    if not entries:
        return "No durable coaching memory entries."

    selected: list[str] = []
    total_chars = 0
    omitted_count = 0
    for entry in reversed(entries):
        prefix_parts = [entry["source_type"]]
        if entry["source_date"]:
            prefix_parts.append(entry["source_date"])
        line = f"- {' | '.join(prefix_parts)}: {entry['content']}"
        next_total = total_chars + len(line) + 1
        if len(selected) >= _COACHING_MEMORY_MAX_ENTRIES or next_total > _COACHING_MEMORY_MAX_CHARS:
            omitted_count += 1
            continue
        selected.append(line)
        total_chars = next_total

    lines = list(reversed(selected))
    if omitted_count:
        lines.insert(
            0,
            f"- {omitted_count} older coaching memory entries omitted from this raw prompt to keep context bounded.",
        )
    return "\n".join(lines)


def _build_question_message(
    workout_content: str,
    question: str,
    prior_questions: list[dict[str, str]] | None = None,
) -> str:
    lines = [
        "SAVED WORKOUT:",
        workout_content.strip(),
        "",
        "USER PROFILE:",
        _read_user_profile(),
    ]

    if prior_questions:
        lines += ["", "RECENT QUESTIONS ABOUT THIS WORKOUT:"]
        for item in prior_questions[-5:]:
            lines.append(f"User: {item['question']}")
            lines.append(f"Coach: {item['answer']}")

    lines += ["", "CURRENT QUESTION:", question.strip(), "", "Answer the current question."]
    return "\n".join(lines)


def _build_revision_discussion_message(
    workout_content: str,
    message: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> str:
    lines = [
        "ORIGINAL SAVED WORKOUT:",
        workout_content.strip(),
        "",
        "USER PROFILE:",
        _read_user_profile(),
    ]
    if prior_messages:
        lines += ["", "REVISION DISCUSSION SO FAR:"]
        for item in prior_messages:
            lines.append(f"User: {item['user_text']}")
            lines.append(f"Coach: {item['assistant_text']}")
    lines += ["", "CURRENT MESSAGE:", message.strip(), "", "Discuss this request without revising the workout yet."]
    return "\n".join(lines)


def _build_revision_apply_message(
    workout_content: str,
    messages: list[dict[str, str]],
    final_instruction: str = "",
) -> str:
    lines = ["ORIGINAL SAVED WORKOUT:", workout_content.strip(), "", "REVISION DISCUSSION:"]
    if messages:
        for item in messages:
            lines.append(f"User: {item['user_text']}")
            lines.append(f"Coach: {item['assistant_text']}")
    else:
        lines.append("(No prior discussion.)")
    if final_instruction.strip():
        lines += [
            "",
            "FINAL INSTRUCTION FROM THE USER (apply this decisively; do not ask about it):",
            final_instruction.strip(),
        ]
    lines += ["", "Apply the agreed changes and return the complete workout."]
    return "\n".join(lines)


def _gemini_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Get a free key at Google AI Studio and set the environment variable."
        )
    return api_key


def generate_workout_markdown(
    day: ScheduleDay,
    note: str = "",
    storage=None,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_api_key())
    user_message = _build_user_message(day, note, storage)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            max_output_tokens=4096,
            temperature=0.7,
        ),
    )

    result = response.text.strip()
    return result if result.endswith("\n") else result + "\n"


def answer_workout_question(
    workout_content: str,
    question: str,
    prior_questions: list[dict[str, str]] | None = None,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_api_key())
    user_message = _build_question_message(workout_content, question, prior_questions)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_QUESTION_SYSTEM_INSTRUCTION,
            max_output_tokens=1024,
            temperature=0.6,
        ),
    )

    return response.text.strip()


def discuss_workout_revision(
    workout_content: str,
    message: str,
    prior_messages: list[dict[str, str]] | None = None,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_build_revision_discussion_message(workout_content, message, prior_messages),
        config=types.GenerateContentConfig(
            system_instruction=_REVISION_DISCUSSION_SYSTEM_INSTRUCTION,
            max_output_tokens=1024,
            temperature=0.4,
        ),
    )
    return response.text.strip()


def revise_workout_markdown(
    workout_content: str,
    messages: list[dict[str, str]],
    final_instruction: str = "",
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_build_revision_apply_message(workout_content, messages, final_instruction),
        config=types.GenerateContentConfig(
            system_instruction=_REVISION_APPLY_SYSTEM_INSTRUCTION,
            max_output_tokens=4096,
            temperature=0.2,
        ),
    )
    result = response.text.strip()
    return result if result.endswith("\n") else result + "\n"


def summarize_app_request(request_text: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"REQUEST:\n{request_text.strip()}\n\nSummarize for the coding agent.",
        config=types.GenerateContentConfig(
            system_instruction=_APP_REQUEST_SUMMARY_SYSTEM_INSTRUCTION,
            max_output_tokens=512,
            temperature=0.2,
        ),
    )
    return response.text.strip()
