---
description: Run the verification gate against an agent's pre-output verification block
argument-hint: Path to the block file, or paste the block
---

# Verify Agent Output

Run the verification gate against a pre-output verification block and report the
result per item.

**Input**: $ARGUMENTS

## Steps

1. If the argument is a file path, use it directly. If the user pasted a block,
   write it to a temporary file first.
2. Run the gate:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verification_gate.py" <block-file>
   ```

   Add `--stack <profile>` when the stack is known, and `--security-path <term>`
   for any project-specific term that should be treated as a security boundary
   (a module name, a route prefix, a table name).

3. Report the outcome using the gate's own per-item output. Exit codes:
   `0` approved · `1` blocked · `2` approved with warnings · `3` no parseable block.

## Reporting rules

Report per item. Do not compute a pass rate, a percentage, or an overall score
— the gate deliberately produces none, because averaging lets a critical failure
hide behind cosmetic successes.

When the gate blocks, state which item blocked and why, then say what would
resolve it. A CONTRADICTED item needs the code fixed or the claim corrected. An
UNVERIFIED item on a security path needs the check actually run.

When the gate reports status inflation, explain it plainly: the agent asserted
OBSERVED on evidence that cannot support it (naming, comments, documentation, or
inference), and the honest status is CLAIMED.

Never reproduce a secret value found in a block. The gate redacts them; keep
them redacted, and note that any committed value should be treated as
compromised.
