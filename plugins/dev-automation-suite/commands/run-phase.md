---
description: Run a dev-automation-suite workflow phase against the current project
argument-hint: Phase name or number, e.g. "review" or "3"
---

# Run Workflow Phase

Run one phase of the eleven-phase lifecycle and report its per-check verdicts.

**Requested phase**: $ARGUMENTS

## Steps

1. If no phase was given, show the model and ask which to run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/suite_orchestrator.py" phases
   ```

2. Run the phase. Default is a dry run; add `--commit` only when the user wants
   phase state persisted to `.dev-suite/`.

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/suite_orchestrator.py" run <phase> "${CLAUDE_PROJECT_DIR}" \
       --targets <changed files> \
       --original <baseline file, if one exists> \
       --verification-block <agent block file, for phases 2/3/5/7>
   ```

3. Report the verdict per check.

## What the exit codes mean

`0` pass · `1` blocking failure, route to the Fix phase · `2` HALT, requires
user intervention · `3` configuration error.

**A HALT is not a failure to retry.** Breaking changes and verification-gate
halts require explicit resolution or user approval. Do not auto-fix a breaking
change; that is how a breaking change ships quietly. Bring it to the user with
what changed and what depends on it.

Phases 2, 3, 5 and 7 are agent-led and require `--verification-block`. Running
them without one returns HALT by design — an unverified agent delivery does not
pass. If the user hasn't got a block, that is the thing to fix, not a flag to
work around.

Skipped diff-based checks are normal on new files and are reported with a
stated reason. Don't treat a SKIPPED check as a failure.
