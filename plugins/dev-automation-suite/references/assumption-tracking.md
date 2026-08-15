# Assumption Tracking

<!-- VENDORED CONTENT — classification model adapted from the common-ground
     command package, synced 2026-08-15. Storage and enforcement are
     reimplemented locally in scripts/ground_file.py; no external services. -->

The verification gate checks what an agent claims about **code**. This covers
the other half: what the project assumes about **itself**.

Work built on an unvalidated premise fails as hard as work built on a
hallucinated API, and it is harder to catch — nothing in the diff is wrong. The
premise was.

## Two independent axes

**Type** records how an assumption was derived. It is immutable. Rewriting how
you came to believe something destroys the record that makes the belief
reviewable, so there is no code path that changes a type.

| Type | Derivation | Maps to gate status |
|---|---|---|
| `stated` | The user said it | OBSERVED |
| `inferred` | Concluded from code, config, or structure | INFERRED |
| `assumed` | A best-practice default applied without confirmation | CLAIMED |
| `uncertain` | A gap or conflict needing clarification | UNVERIFIED |

**Tier** records current confidence. It moves freely as evidence arrives.

| Tier | Meaning | How to act |
|---|---|---|
| `ESTABLISHED` | Validated; treat as a premise | Act without re-asking |
| `WORKING` | Reasonable inference | Use it, but surface if contradicted |
| `OPEN` | Unvalidated | Ask before deciding anything on it |

This is the same split as severity and confidence in the evidence model, for the
same reason: conflating derivation with confidence produces both false alarm and
false assurance. An `assumed` premise sitting at `ESTABLISHED` is a specific,
detectable smell — a default that got promoted without anyone stating a basis —
and `ground_file.py check` reports it.

## Default tiers are derived, not fixed

`add` picks a tier from type and impact rather than defaulting everything to the
middle:

- `uncertain` → `OPEN` always
- `stated` → `ESTABLISHED`
- anything touching architecture, security, data, or money → `OPEN`
- otherwise → `WORKING`

High-impact premises start OPEN because the cost of being wrong about
authorization or a data model is paid much later than the cost of asking now.

## Enforcement

```bash
python3 scripts/ground_file.py --project-root . add \
    "Auth model" "Authorization uses role-based permission checks" --type inferred

python3 scripts/ground_file.py --project-root . check
python3 scripts/ground_file.py --project-root . list
python3 scripts/ground_file.py --project-root . tier A2 ESTABLISHED
```

`check` exits `1` when a high-impact premise is OPEN, `2` on warnings, `0` clean.
Registered as a halting check: an unvalidated premise is not something the Fix
phase can repair, because the answer lives with the user.

Findings are per premise. No aggregate confidence score is produced — one
unvalidated high-impact premise is a blocked premise regardless of how many
others are established.

## Cross-checking a verification block

The convergence that makes this more than a notepad:

```bash
python3 scripts/verification_gate.py block.md --ground-file auto --project-root .
```

Each verification item is matched against OPEN premises by distinctive term
overlap. Two or more shared terms is treated as a reference; one is coincidence.
An item resting on an OPEN high-impact premise blocks; a low-impact one warns.

This catches the case no other check can: an item that is entirely correct about
the code — source read, evidence at tier 3 — and still worthless, because the
model it faithfully implements was never the agreed one.

A ground file that cannot be read is an error, not a skip. Silently continuing
would turn a configuration mistake into an unexplained pass.

## Storage

```
~/.claude/common-ground/{project-id}/
├── COMMON-GROUND.md      human-readable, by tier
└── ground.index.json     machine-readable, consumed by the gate
```

Project id comes from the git remote, normalised; failing that, from the path
with a `local/` prefix so the difference is visible rather than implied. Both
files are always written together — an index that has drifted from the markdown
is worse than having only one, because each reader trusts a different version.

Override the store root with `--store` for a project-local ground file.

## Staleness

An `ESTABLISHED` premise validated a year ago is not established; it is stale.
`check` flags anything past `--max-age-days` (default 90). `validate` refreshes
timestamps on non-OPEN items only: an unanswered question does not become
current by being timestamped.
