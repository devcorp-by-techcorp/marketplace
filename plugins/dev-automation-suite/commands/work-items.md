---
description: Manage local epics and tickets, and compute parallel execution waves
argument-hint: "list | epic <title> | ticket <epic> <title> | waves <epic> | status <id> <state>"
---

# Work Items

Local file-based epic and ticket tracking. No external services: items are
markdown under `.dev-suite/work/`, so they live with the code and travel with
the branch.

**Arguments:** $ARGUMENTS

```bash
WI="${CLAUDE_PLUGIN_ROOT}/scripts/work_items.py"
python3 "$WI" --project-root "${CLAUDE_PROJECT_DIR}" list
python3 "$WI" --project-root "${CLAUDE_PROJECT_DIR}" epic "<title>"
python3 "$WI" --project-root "${CLAUDE_PROJECT_DIR}" ticket <EPIC-n> "<title>" \
    --body "<what to do>" --acceptance "<criterion>" ... --depends-on <T-n> ...
python3 "$WI" --project-root "${CLAUDE_PROJECT_DIR}" waves <EPIC-n>
python3 "$WI" --project-root "${CLAUDE_PROJECT_DIR}" status <T-n> <state>
```

States: `todo`, `in-progress`, `in-review`, `done`, `blocked`.

## Writing a ticket worth executing

Always give `--body` and `--acceptance`. A ticket without acceptance criteria has
no definition of finished, so any output can be argued to satisfy it; a ticket
without a description forces an executing agent to infer the work from the title.
The tool names each missing piece — treat those warnings as work to do, not
noise to skip.

Keep tickets self-contained: file paths, the approach, and the criteria, so the
ticket can be picked up without reading the whole plan.

## Ordering

`waves` groups independent tickets so each wave can run in parallel. Work through
waves in order.

Starting a ticket with incomplete dependencies is refused, and a dependency cycle
is reported rather than resolved — do not work around either. An arbitrary order
through a cycle produces work done in the wrong sequence with nothing indicating
it went wrong.

## Editing

The markdown files are the source of truth; `index.json` is derived and
regenerated. Edit the markdown, never the index.
