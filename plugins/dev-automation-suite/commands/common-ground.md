---
description: Surface, record, and validate the project assumptions work is built on
argument-hint: "[--list] [--check] [--graph]"
---

# Common Ground

Surface the assumptions this project is operating on so they can be validated
before work depends on them.

**Arguments:** $ARGUMENTS

| Flag | Mode |
|---|---|
| (none) | Surface assumptions, then record the user's decisions |
| `--list` | Read-only view of what is tracked |
| `--check` | Report premise findings; blocks on OPEN high-impact premises |
| `--graph` | Emit a mermaid diagram of the reasoning behind the assumptions |

Read `references/assumption-tracking.md` for the type and tier model before
classifying anything.

## Default mode

1. **Gather candidates.** Read config and manifest files, the project structure,
   and this conversation. Do not guess: each candidate needs a stated basis.

2. **Classify each one.** Type records how it was derived —
   `stated`, `inferred`, `assumed`, `uncertain`. Assign honestly. An
   industry-standard default applied without confirmation is `assumed`, not
   `inferred`, however reasonable it is.

3. **Ask the user.** Present the candidates and let them choose what to track
   and correct the tiers. Ask directly about anything classified `uncertain` —
   those are the ones worth a question.

4. **Record.** For each confirmed assumption:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ground_file.py" --project-root "${CLAUDE_PROJECT_DIR}" \
       add "<title>" "<assumption>" --type <type> --evidence "<basis>"
   ```

   Omit `--tier` unless the user set one. The default is derived from type and
   impact, which is usually more honest than a tier chosen in the moment.

## --list and --check

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ground_file.py" --project-root "${CLAUDE_PROJECT_DIR}" list
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ground_file.py" --project-root "${CLAUDE_PROJECT_DIR}" check
```

`check` exits `1` when a high-impact premise is OPEN. Treat that as a question
for the user, not a problem to route into the Fix phase — the answer is not in
the codebase.

## --graph

Generate a mermaid flowchart of the decisions behind the tracked assumptions:
the branch points, what was chosen, what was not, and where uncertainty sits.
Keep the alternatives in the diagram rather than pruning them; a graph showing
only the chosen path hides the reasoning it exists to expose.

Render it inline. Only write a file if the user asks for one.

## Rules

- **Never change a type.** Types are the audit trail. If a derivation was
  recorded wrongly, say so and add a corrected entry rather than editing history.
- **Never promote a tier without the user.** Promotion is their judgment.
- **Do not launder an assumption into a fact.** If it was `assumed`, it stays
  `assumed` however confident everyone becomes.
- **Report per premise.** No confidence percentage, no "8 of 10 validated".
