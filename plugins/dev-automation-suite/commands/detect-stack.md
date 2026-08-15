---
description: Detect the project's stack profile and emit the matching verification checklist
argument-hint: Optional project subdirectory
---

# Detect Stack Profile

Determine which stack-specific verification items apply to this project, so
agent briefs carry the right checklist rather than a generic one.

**Target**: $ARGUMENTS (defaults to the project root)

## Steps

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stack_profile.py" "${CLAUDE_PROJECT_DIR}"
```

Add `--checklist` for numbered items ready to append to a verification block
(numbered from 8, continuing the base seven-item checklist), or `--json` for
machine-readable output.

## Reading the result

Profiles compose. A repository holding an Expo app and a Flask API returns both,
because "async error handling" means different things in an Express route and a
React Native screen. The `generic` profile is always present.

Every profile states the evidence that triggered it. If a profile looks wrong,
check its evidence line rather than assuming the detector is broken.

If only `generic` comes back, detection found no stack signature. It reads
manifests to depth 3 — in a monorepo, point it at the subdirectory holding the
manifest rather than the repository root.

Use the detected items in agent briefs. Don't paste Python-specific checks into
a React Native agent's brief, and don't substitute invented generic prose for
the concrete, runnable checks the profile provides.
