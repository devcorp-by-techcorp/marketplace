---
name: dev-automation-suite
description: "Complete autonomous development system covering the full lifecycle: analyse, build, review, test, fix, simplify, validate, harden, observe, ship. Orchestrates specialised subagents through eleven phases with script-enforced quality gates, evidence-driven agent output verification, stack-aware check profiles, and iterative self-correction loops. Rejects band-aid fixes, halts on breaking changes, and blocks unverified agent deliveries at the SubagentStop hook. Use whenever building features, fixing bugs, refactoring, hardening, or shipping — any multi-step development work needing autonomous production with enforced quality. Triggers on: 'build', 'implement', 'develop', 'create feature', 'fix bug', 'refactor', 'harden', 'ship', 'release', 'automate', 'iterate until done', 'development workflow', 'quality gate', 'verify output', 'build and test'."
license: Apache-2.0
metadata:
  version: 3.3.2
  lineages: automate-dev, production-code-quality, agent-output-verification
---

# Development Automation Suite

Autonomous, iterative development across the full delivery lifecycle. Every
phase has an owner, a script contract, and a gate. Zero tolerance for breaking
changes, band-aid fixes, or unverified agent output.

## What this suite is

Three lineages merged into one system:

| Lineage | Contributed |
|---|---|
| `automate-dev` | The build-review-test-fix loop, iteration protocols, stall detection, token budgeting |
| `production-code-quality` | Breaking-change detection, compatibility, preservation, self-assessment |
| `agent-output-verification` | The evidence model and the pre-output gate on agent deliveries |
| `common-ground` | Premise tracking by type and tier, cross-checked by the gate |
| project lifecycle set | The outer intake→retrospective loop, external services stripped |

Their scripts had incompatible CLI conventions and undocumented interfaces.
`scripts/script_registry.py` declares every contract once; nothing else in the
suite hard-codes a call shape.

## Core principles

1. **Iterate until done** — loop through build → review → test → fix until every
   issue is permanently resolved.
2. **No band-aids** — every fix addresses root cause. Suppressions, workarounds,
   and temporary patches are rejected programmatically.
3. **No breaking changes** — existing functionality is preserved unconditionally.
   Detection halts the workflow rather than routing to Fix.
4. **No unverified delivery** — an agent that produced code must emit a
   verification block. No block, no delivery.
5. **No unvalidated premise** — work resting on an OPEN high-impact assumption
   is blocked. Correct code built on the wrong model is still wrong.
6. **No aggregate scores** — one blocking item is a blocked delivery regardless
   of how many others passed. Averaging lets a critical failure hide behind
   cosmetic successes.
7. **Simplicity is strength** — simplified for clarity without losing capability.
8. **Production-ready always** — complete error handling, security, validation.

## Phase model

```
 0 BOOTSTRAP ──▸ 1 ANALYSE ──▸ 2 BUILD ──▸ 3 REVIEW ──▸ 4 TEST
                     ▲                                     │
                     │         6 SIMPLIFY ◂── 5 FIX ◂───────┘
                     │              │
                     │         7 VALIDATE ──▸ pass? ──▸ 8 HARDEN
                     │              │ no                    │
                     └──────────────┘                  9 OBSERVE
                        (iteration loop)                    │
                                                       10 SHIP
```

| # | Phase | Purpose | Agent-led | Gate required |
|---|-------|---------|-----------|---------------|
| 0 | Bootstrap | Stack detection, premise surfacing, budget init | — | — |
| 1 | Analyse | Inventory, dependency map, acceptance criteria | ✓ explorer | — |
| 2 | Build | Implementation | ✓ architect | ✓ |
| 3 | Review | Script checks + agent review | ✓ reviewer | ✓ |
| 4 | Test | Test execution | — | — |
| 5 | Fix | Root-cause fixes, band-aid rejection | ✓ | ✓ |
| 6 | Simplify | Complexity reduction, behaviour preserved | — | — |
| 7 | Validate | Full quality gate | ✓ reviewer | ✓ |
| 8 | Harden | Security pass | ✓ | — |
| 9 | Observe | Observability and performance pass | ✓ | — |
| 10 | Ship | Deployment readiness, docs, release | — | — |

Phases 8–10 come from the lifecycle suite; 1–7 are the core loop. Read
`references/workflow-phases.md` for per-phase detail.

These eleven phases cover **one unit of work**. The outer project loop —
intake, discovery, planning, execution, retrospective — is in
`references/project-lifecycle.md`. They nest: one pass through outer
Execution runs the full inner loop for a single ticket. Both are local files
and CLI only; no external tracker or documentation service is involved.

## Running it

```bash
# Show the phase model and what each phase owns
python3 scripts/suite_orchestrator.py phases

# Bootstrap: detect stack, initialise budget
python3 scripts/suite_orchestrator.py run bootstrap <project_root>
python3 scripts/token_budget_monitor.py init <project_root> --difficulty medium

# Run a phase (dry run by default; --commit persists state)
python3 scripts/suite_orchestrator.py run review <project_root> \
    --targets app/services/mailer.py \
    --original .baseline/mailer.py \
    --verification-block .dev-suite/agent-block.md \
    --commit
```

Exit codes: `0` pass · `1` blocking failure → Fix phase · `2` HALT → user
intervention · `3` configuration error.

Agent-led phases fail closed. Running phase 3, 5, or 7 without
`--verification-block` returns HALT — an unverified agent delivery does not
pass, by design.

## Agent roster

| Agent | Role | Model | Effort | Phases |
|-------|------|-------|--------|--------|
| **code-explorer** | Codebase tracing, pattern discovery | `claude-sonnet-5` | high | 1 |
| **code-architect** | Architecture design, implementation blueprints | `claude-opus-5` | xhigh | 2 |
| **code-reviewer** | Quality review — simplicity, correctness, conventions | `claude-opus-5` | xhigh | 3, 7 |

All three carry an `## Exit Criteria — Pre-Output Verification` section. That
section is the contract the `SubagentStop` hook enforces; it is not optional
documentation. See `references/agent-roster.md` for the wider agent ecosystem
and how to onboard additional agents into the gate.

Agents provide **judgment**. Scripts provide **rule enforcement**. Use both.

## Script registry

Seventeen scripts, one declared contract each. Query it directly:

```bash
python3 scripts/script_registry.py          # full wiring report
```

| Script | Purpose | Phases |
|--------|---------|--------|
| `suite_orchestrator.py` | Unified phase dispatch | all |
| `script_registry.py` | Invocation contracts, exit semantics, phase map | — |
| `verification_gate.py` | Parses/enforces agent verification blocks | 2,3,5,7 |
| `stack_profile.py` | Stack detection → check profile | 0,1 |
| `ground_file.py` | Premise tracking; halts on OPEN high-impact premises | 0,1,7 |
| `work_items.py` | Local epic/ticket tracking, dependency waves | 1,10 |
| `review_packet.py` | Builds/verifies the blind-review packet | 3,7 |
| `dev_orchestrator.py` | Phase engine (analyse/test/validate) | 1,4,7 |
| `code_reviewer.py` | Band-aid, security, breaking-change review | 3,7 |
| `code_simplifier.py` | Nesting, duplication, naming | 6 |
| `fix_validator.py` | Confirms fixes are structural | 5 |
| `iteration_planner.py` | Plans, stall detection, escalation | 1,7 |
| `deployment_readiness.py` | Pre-ship verification | 8,10 |
| `token_budget_monitor.py` | Budget enforcement, cost reporting | all |
| `breaking_change_detector.py` | Public API removal/signature changes | 3,7 |
| `compatibility_checker.py` | Import/signature compatibility | 3,7 |
| `functionality_preserver.py` | Feature preservation | 3,7 |
| `rn_analyzer.py` | React Native / Expo analysis | 3 |
| `self_assessment.py` | Consolidated quality self-assessment | 7 |

`breaking_change_detector`, `verification_gate`, and `review_packet` **halt**
rather than fail: their failures require explicit resolution and are never
auto-routed to Fix. For `review_packet` there is nothing in the code to fix —
the review was never conducted under the conditions it claims.

## The verification gate

The enforcement point that makes agent output trustworthy. An agent writes a
verification block; `verification_gate.py` parses it per item and applies rules
a prose checklist cannot enforce on itself:

- **CONTRADICTED** on any item → blocked
- **UNVERIFIED** on a security-sensitive item → blocked
- **Status inflation** (OBSERVED claimed on naming/comment/inference evidence,
  tiers 8–10) → downgraded to CLAIMED and reported
- **Aggregate score** present → the block is invalid
- **Literal secrets** → redacted to location and type before reporting

Wired at `SubagentStop` via `hooks/hooks.json`, scoped by `matcher` to this
plugin's own three agents. The gate demands a verification block, and the
built-in agents — `Explore`, `Plan`, `general-purpose` — have never heard of
one: an unscoped matcher would block every subagent in every session the
plugin is enabled for. Widen the matcher to `*` only after the agents you are
widening it over actually emit blocks.

Read `references/output-verification.md` for the full evidence model and
`references/hooks.md` for the payload contract.

## Independent review

Phases 3 and 7 are where one agent judges another's output, and a reviewer that
has read the author's account is not judging — it is agreeing with an argument.
The leak is rarely deliberate. An orchestrator twenty turns into the problem
writes "review the retry logic I added around the timeout", and the reviewer
now checks whether backoff was implemented correctly rather than whether
retrying was the right response at all.

So a reviewing agent receives exactly two things: the **original task**,
verbatim and pinned by hash before work began, and the **completed work** as a
diff. Withheld: the reasoning, the steps, the author's own verification block,
and the author's assessment of the result.

```bash
python3 scripts/review_packet.py record <root> --task-file request.txt
python3 scripts/review_packet.py build  <root> --diff work.diff -o packet.md
python3 scripts/suite_orchestrator.py run review <root> \
    --review-packet packet.md --verification-block block.md --commit
```

Four layers, because no one of them is sufficient:

| Layer | Mechanism |
|---|---|
| Structural | `workflows/independent-review.js` — results live in script variables, so there is no author's account for a reviewer prompt to be built from |
| Mechanical | `review_packet.py check` — eight named rules; prose rules matched outside code fences, both section hashes verified |
| Tool boundary | `hooks/reviewer-isolation.sh` on `PreToolUse` — reads into `.dev-suite/`, logs, and transcripts are denied |
| Contractual | the same hook on `SubagentStart` — injects the blind-review contract so it does not depend on the caller |

Pinning the task is the least obvious rule and does the most work: an
orchestrator asked to restate the request compresses its own conclusions into
it. See `references/independent-review.md`.

Phases 2 and 5 are agent-led but *produce* work rather than judge it — they
need a verification block and no packet.

## Premise tracking

The gate checks what an agent claims about code. Premise tracking covers what
the project assumes about itself — and those failures are harder to catch,
because nothing in the diff is wrong. The premise was.

Assumptions carry two independent values: a **type** recording how it was
derived (immutable — it is the audit trail) and a **tier** recording current
confidence (freely adjustable). High-impact premises default to `OPEN`.

```bash
python3 scripts/ground_file.py --project-root . check
python3 scripts/verification_gate.py block.md --ground-file auto --project-root .
```

With `--ground-file`, each verification item is matched against OPEN premises.
An item resting on an OPEN high-impact premise **blocks** — even when the item
is entirely correct about the code, because faithfully implementing the wrong
model is still wrong.

See `references/assumption-tracking.md`.

## Stack profiles

Stack-specific checks are **detected**, not assumed. `stack_profile.py` reads
the project's manifests and returns composing profiles — `python-flask`,
`typescript-rn`, `node-express`, `frontend-web`, plus `generic` always. A repo
holding an Expo app and a Flask API gets both, because "async error handling"
means different things in an Express route and a React Native screen.

```bash
python3 scripts/stack_profile.py <project_root> --checklist
```

See `references/stack-profiles.md` to add a profile.

## Model routing

Routing follows one rule: **validation, conductor, and complex work → Opus 5;
report writing and discovery work → Sonnet 5 at `high`.**

| Difficulty | Model | Effort | Examples |
|-----------|-------|--------|----------|
| low | `claude-sonnet-5` | default | Simple reads, formatting |
| medium | `claude-sonnet-5` | high | Discovery, tracing, report writing |
| **high** | **`claude-opus-5`** | **xhigh** | Review, architecture, quality gates |
| xhigh | **`claude-opus-5`** | **xhigh** | Complex refactoring, subtle debugging |
| max | **`claude-opus-5`** | **max** | Formal verification, security audits |

Opus 5 is required for any agent reviewing another agent's work, all
architectural decisions, and Phase 7 validation — that is validation work,
and validation is the one place a cheaper model costs more than it saves.
Identifiers are pinned rather than aliased, so a model retirement fails
loudly instead of drifting. See `references/model-deployment.md`.

## Reference documentation

Loaded on demand to preserve context budget.

| Reference | When to read |
|-----------|-------------|
| `references/workflow-phases.md` | Per-phase instructions and examples |
| `references/output-verification.md` | Gate rules, evidence model, embedding |
| `references/quality-gates.md` | Thresholds, precedence, pass/fail criteria |
| `references/agent-roster.md` | Agent definitions, onboarding new agents |
| `references/stack-profiles.md` | Adding or amending a stack profile |
| `references/assumption-tracking.md` | Premise types, tiers, gate cross-check |
| `references/project-lifecycle.md` | The outer intake→retrospective loop |
| `references/independent-review.md` | Blind review: the packet, the four layers |
| `references/hooks.md` | Hook wiring and payload contract |
| `references/iteration-protocols.md` | Loop management, stall detection |
| `references/code-simplification.md` | Simplification rules |
| `references/model-deployment.md` | Routing strategy, difficulty classification |
| `references/token-budgeting.md` | Phase budgets, caching, cost patterns |
| `references/feature-development.md` | Guided feature development mode |

## Testing

```bash
python3 tests/test_suite.py     # 130 regression tests, standard library only
```

Covers the gate rules, premise cross-check, registry integrity, stack
detection, work-item ordering, hook payload handling, and the blind-review
packet and isolation hook. Run before packaging any change.

## Installation

### As a Claude Code plugin (recommended)

The package is a complete plugin: manifest at `.claude-plugin/plugin.json`,
agents, slash commands, the `SubagentStop` hook, and `bin/` wrappers.

It is distributed through the `techcorp-plugins` marketplace, whose manifest
sits at the root of the hosting repository and points at this plugin's
directory:

```bash
claude plugin marketplace add devcorp-by-techcorp/marketplace
claude plugin install dev-automation-suite@techcorp-plugins
```

From a local checkout, add the **repository root** — not the plugin directory.
`source` paths resolve relative to the manifest, so pointing at the plugin
directory finds no marketplace at all:

```bash
claude plugin marketplace add /path/to/marketplace
```

Or without installing at all:

```bash
# Try it for one session
claude --plugin-dir /path/to/marketplace/plugins/dev-automation-suite

# Or scaffold it as a skills-directory plugin, loaded on next session
cp -r plugins/dev-automation-suite ~/.claude/skills/
```

Verify before relying on it:

```bash
claude plugin validate /path/to/marketplace/plugins/dev-automation-suite
claude plugin details dev-automation-suite
```

What the plugin contributes once enabled:

| Component | Appears as |
|---|---|
| Skill | `/dev-automation-suite` |
| Commands | `:run-phase`, `:verify-output`, `:detect-stack`, `:common-ground`, `:work-items`, `:feature-development` |
| Agents | `dev-automation-suite:code-explorer`, `:code-architect`, `:code-reviewer` in the `@`-mention typeahead |
| Hooks | `SubagentStop` → the verification gate, on this plugin's three agents. `PreToolUse` + `SubagentStart` → reviewer isolation |
| Workflow | `/dev-automation-suite:independent-review` |
| Executables | `dev-suite`, `dev-suite-verify`, `dev-suite-stack`, `dev-suite-ground`, `dev-suite-work` |

The `bin/` wrappers resolve the suite root from their own location, so they work
both as plugin commands and when run directly from a checkout.

Hook and agent changes need `/reload-plugins` or a restart; `SKILL.md` edits
take effect immediately.

### Manual install (no plugin)

```bash
cp dev-automation-suite/agents/*.md   .claude/agents/
cp dev-automation-suite/commands/*.md .claude/commands/
cp dev-automation-suite/hooks/hooks.json .claude/hooks/
chmod +x dev-automation-suite/hooks/*.sh dev-automation-suite/bin/*
```

Set `CLAUDE_PLUGIN_ROOT` to the suite directory so the hook resolves its paths.

### Claude.ai Projects

Upload the `.skill` or `.zip`. Agents and hooks don't apply there; the suite
degrades to script-only operation, and `verification_gate.py` still runs against
any block pasted into the conversation.

### Requirements

Python 3.8+, Bash for hooks, Claude Code v2.1.142+ for root-`SKILL.md` autoload
and v2.1.143+ for `displayName`. No third-party packages: standard library only
throughout, so nothing is installed into the plugin cache.

## Troubleshooting

**Phase halts with "requires a pre-output verification block"** — working as
designed. Supply `--verification-block`, or have the agent emit one.

**`missing_scripts()` reports absences** — the package is incomplete; re-extract.
The orchestrator refuses to run rather than fail mid-phase.

**Stack profile returns only `generic`** — detection reads manifests to depth 3.
In a monorepo, point it at the subdirectory that holds the manifest.

**Band-aid detected** — reject the fix, re-analyse root cause, implement a
structural fix. After three attempts on one issue, escalate with full context.
