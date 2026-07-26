# User Profile (local-only input)

This directory is for user-authored coaching context, not public source code.
Create one or more Markdown files here after cloning if the generated workouts
should reflect a particular training history, preference, limitation, or
equipment setup.

The application also works with this directory empty. The repository ignores
every profile file except this usage guide so personal details do not become
part of a normal public commit. Do not use `git add --force` on profile files
unless you have deliberately removed all private information.

Possible local files include:

- `athlete_profile.md` for goals and training background
- `preferences.md` for durable preferences
- `user_info/` for equipment, constraints, or workout examples

When an AI feature runs, the relevant profile content is included in the
request context sent to Gemini. Keep sensitive information out of these files
unless that data flow is acceptable to you.
