# Output Verification — Gate Rules and Evidence Model

The enforcement layer that makes agent-produced code trustworthy. Vendored from
the `agent-output-verification` skill so this suite stays self-contained.

<!-- VENDORED CONTENT — evidence model adapted from agent-output-verification
     v1.0.0, synced 2026-08-11. Amend upstream and re-vendor; see CHANGELOG.md. -->

## Why the gate exists

Unconstrained agents present code as finished without re-reading it. Role and
persona framing suppresses self-checking, which is why every block in this suite
uses task-context framing ("the output must satisfy X") rather than persona
framing ("you are a careful engineer who...").

A checklist an agent can ignore without consequence is not a gate. Every item
carries a required status, and stated conditions block delivery.

## Why binary PASS/FAIL is insufficient

A binary gate gives an agent no honest way to say "I couldn't check this."
Faced with PASS or FAIL and having done neither, agents reliably write PASS.
The status vocabulary exists to make honest non-verification cheaper than a
false pass. That is the entire mechanism.

## Status vocabulary

| Status | Meaning |
|---|---|
| **OBSERVED** | Directly established — the check was run, or the code was read |
| **INFERRED** | Reasonably derived from what was observed, not demonstrated |
| **CLAIMED** | Asserted by docs, comments, naming, or the agent's own prior statement |
| **UNVERIFIED** | Could not be checked. State why |
| **CONTRADICTED** | The code does something materially different from what was stated |

`UNVERIFIED` with a stated reason is a good outcome. `CLAIMED` presented as
`OBSERVED` is the failure this model prevents.

Worked example — "referenced APIs are real":

- **OBSERVED**: `tsc --noEmit` run, exit 0; every referenced type resolved
- **INFERRED**: the method appears in three sibling modules with identical signature
- **CLAIMED**: the method name follows the library's convention and looked right
- **CONTRADICTED**: `client.sendBatch()` does not exist; the library exposes
  `client.send()` taking an array

The CLAIMED row is exactly how hallucinated APIs reach delivery.

## Evidence quality hierarchy

State the tier supporting each status. Lower tiers cannot override stronger
contradictory evidence.

| Tier | Evidence |
|---|---|
| 1 | Independently reproduced runtime behaviour |
| 2 | Reproducible automated test result |
| 3 | Direct source-code evidence (the file was actually read) |
| 4 | Configuration / dependency-manifest evidence |
| 5 | Build / CI evidence |
| 6 | Version-control evidence |
| 7 | Documentation |
| 8 | Comments |
| 9 | Naming / convention |
| 10 | Agent inference |

**Tiers 8–10 cannot support OBSERVED.** `verification_gate.py` detects this
automatically and downgrades the status to CLAIMED, reporting the inflation.
When the item is security-sensitive, the downgrade blocks delivery.

Where evidence spans tiers, the strongest present wins: text citing both a
passing test run and a naming convention resolves to tier 2.

## Confidence and severity are independent

Confidence describes evidence strength. Severity describes consequence if the
problem is real. Conflating them produces both false alarm and false assurance.

| Confidence | Basis |
|---|---|
| Very High | Runtime evidence + source inspection + independent validation |
| High | Strong source evidence + successful automated verification |
| Medium | Strong static evidence, no runtime validation |
| Low | Indirect evidence or incomplete visibility |
| Very Low | Documentation, comments, naming, or assumption only |

| Severity | Meaning |
|---|---|
| Critical | Immediate or highly consequential compromise/failure |
| High | Significant exploitable weakness or material functional failure |
| Medium | Meaningful weakness requiring remediation |
| Low | Limited risk or maintainability issue |
| Informational | Observation without demonstrated material risk |

`Severity: High / Confidence: Low` is legitimate and valuable: *if confirmed,
this matters a lot; current evidence cannot confirm it.* Never raise severity
because confidence is high; never present an uncertain finding as confirmed.

## Security escalation rule

A functional defect escalates when it weakens a security boundary. Escalate
when the code touches:

authentication · authorization · identity · privilege boundaries · tenant or
jurisdiction isolation · audit logging · input validation · sensitive or
regulated data · financial transactions · destructive operations

"Password reset behaves incorrectly" is a High functional issue and a Critical
security issue. Report at the escalated level.

`verification_gate.py` matches these terms against each item's check text and
evidence, and flags severity understatement on matched items.

## Self-claim reconciliation

Before delivering, re-read the summary or commit message just written and check
it against the code actually produced. Any mismatch is CONTRADICTED: fix the
code or correct the claim. Agents routinely write "all async paths now have
error handling" over code where two paths don't. This costs one re-read and
catches a category of error nothing else in the gate will.

## Secret handling

Never reproduce credential values in a verification report. Report location and
type only, and treat anything found committed as potentially compromised.

```
BAD:   JWT_SECRET=abc123... found in config/settings.py:14
GOOD:  Hardcoded secret [JWT signing key] at config/settings.py:14 — value [REDACTED]
```

`verification_gate.py` redacts automatically and reports what it removed.

## No aggregate pass score

Never collapse the block into a number or percentage. Five items OBSERVED and
one CONTRADICTED on an authorization path is not "83% passing" — it is a blocked
delivery. The gate rejects any block containing an aggregate score, because
averaging lets a critical failure hide behind cosmetic successes.

## Limitations statement

Close the block by naming what constrained it: no runtime environment, no
database access, dependency not installed, files outside the visible working
set. Limitations make the confidence ratings interpretable, and their absence
is itself a warning sign.

## Choosing a template

| Template | Use when |
|---|---|
| `assets/verification-block-template.md` | Small, low-risk, fully runnable changes where the agent can execute every check |
| `assets/verification-block-evidence.md` | The delivery touches a security boundary, the agent cannot run what it wrote, or phase difficulty is `high`+ |

Don't impose the heavier template where it will be rubber-stamped — an
over-specified gate gets skimmed, which is worse than a short one followed.

## Embedding in a prompt

Insert as its own labelled section (`## Pre-Output Verification` or
`## Delivery Gate`) after the task and requirements sections, before any
output-format instructions. The agent needs full context on what "correct"
means before being told to verify against it.

Wire it into the prompt's structure so it reads as a gate between "code written"
and "code delivered" — not an afterthought appended to skim.

## Anti-patterns

- **Checklist as decoration** — no stated blocking condition means no gate
- **Over-specifying** — 20 items get skimmed; 7 with clear criteria get followed
- **Persona framing** — weaker than task-context framing, every time
- **Aggregate pass scores** — 6/7 is a blocked delivery, not 86%
- **Status inflation** — OBSERVED on a plausible-looking name manufactures false
  assurance and is worse than an honest UNVERIFIED
