# Agent Teams Integration — Mode 3 Reference

This reference defines when and how the automate-dev workflow autonomously
escalates from solo subagents (Modes 1 & 2) to coordinated agent teams
(Mode 3). The team-agents toolkit, slash commands, and internal skill
library are bundled with this skill.

## Table of Contents

1. [Activation Criteria](#activation-criteria)
2. [Team Agents](#team-agents)
3. [Slash Commands by Phase](#slash-commands-by-phase)
4. [Preset Selection Matrix](#preset-selection-matrix)
5. [Internal Skills Mapping](#internal-skills-mapping)
6. [Quality Gate Preservation](#quality-gate-preservation)
7. [Lifecycle Discipline](#lifecycle-discipline)
8. [Token Budget Adjustments](#token-budget-adjustments)
9. [Pre-flight Checklist](#pre-flight-checklist)
10. [Decision Trees](#decision-trees)

---

## Activation Criteria

Mode 3 (Team Coordination) activates **autonomously** when ANY of the
following is true for the current task:

| Trigger | Recommended Command |
|---------|---------------------|
| Work decomposes into ≥3 independent file-ownership streams | `/team-feature` or `/team-spawn fullstack` |
| Spans frontend + backend + tests + (optional) infra | `/team-spawn fullstack` |
| Codebase migration / framework upgrade / API version bump | `/team-spawn migration` |
| Bug surface has ≥2 plausible root causes after Phase 1 analysis | `/team-debug --hypotheses 3` |
| Review needs ≥4 quality dimensions OR security focus | `/team-review --reviewers ...` or `/team-spawn security` |
| Phase 1 needs research across ≥3 distinct areas | `/team-spawn research` |
| User explicitly requests "team", "parallel agents", "multi-agent" | Match request |

**Negative signals** (stay solo / Mode 1 or 2):

- Single-file or tightly-scoped change
- Bug with one obvious cause
- Review of <4 dimensions (the standard `code-reviewer × 3` is sufficient)
- Quick refactor with no cross-cutting concerns
- Environment lacks `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

If a negative signal applies, do not waste resources on team coordination
overhead — the solo subagent patterns from `references/agents.md` are
faster and cheaper.

---

## Team Agents

Four team-agent personas live in `agent-teams/agents/`. Each is
`model: claude-opus-4-8` to align with the automate-dev `xhigh` quality bar.

| Agent | Colour | Role | Key Constraints |
|-------|--------|------|-----------------|
| **team-lead** | blue | Decompose work, assign file ownership, monitor, synthesise, manage shutdown | One owner per file; uses TaskCreate / TaskUpdate / SendMessage |
| **team-implementer** | yellow | Build within strict file ownership; coordinate at integration points | Never modifies unassigned files; references contracts, never mutates them |
| **team-reviewer** | green | Single-dimension review (security / performance / architecture / testing / accessibility) | Stays in lane; produces structured findings with `file:line` + severity + fix |
| **team-debugger** | red | Investigate one assigned hypothesis with evidence and confidence rating | Reports both confirming AND contradicting evidence; no scope creep |

Read each agent definition before instructing the team-lead — the
agents enforce these constraints internally and will reject out-of-scope work.

---

## Slash Commands by Phase

### Phase 1 (Analyse) → `/team-spawn research`

When the analysis target spans multiple distinct areas (e.g. backend Python
service + Next.js frontend + Terraform infra + API docs):

```
/team-spawn research --members 3 --name analyse-{slug}
```

Each `general-purpose` teammate is given one area and the same output
template. Apply `agent-teams/skills/task-coordination-strategies/SKILL.md` to write
the per-teammate task descriptions. Synthesise into the iteration plan,
then continue Phase 1 inventory.

### Phase 2 (Build) → `/team-feature` / `/team-spawn fullstack` / `/team-spawn migration`

When the implementation breaks cleanly into ≥3 work streams with
non-overlapping file ownership:

```
# Standard parallel build
/team-feature "<description>" --team-size 2 --plan-first

# Full-stack split
/team-spawn fullstack --name <feature-team>

# Large refactor / migration
/team-spawn migration --name <migration-team>
```

Mandatory pre-work:

1. Read `agent-teams/skills/parallel-feature-development/SKILL.md` for ownership strategy
2. Read `agent-teams/skills/team-composition-patterns/SKILL.md` for team sizing
3. Use `--plan-first` so the user approves the decomposition before spawn
4. Define interface contracts in advance (lead-owned, immutable mid-stream)

### Phase 3 (Review) and Phase 7 (Validate) → `/team-review` / `/team-spawn security`

When the change touches authentication, data layers, public APIs, UI
accessibility, or performance hot paths:

```
# Multi-dimensional review (default trio)
/team-review <target> --reviewers security,performance,architecture

# Add testing + accessibility for full feature work
/team-review <target> --reviewers security,performance,architecture,testing,accessibility

# Comprehensive security audit
/team-spawn security --name security-audit
```

`<target>` accepts: file path, directory, git diff range (e.g. `main...HEAD`),
PR number (`#123`).

Mandatory pre-work:

1. Read `agent-teams/skills/multi-reviewer-patterns/SKILL.md` for dimension allocation
2. Apply the recommended-combinations table (API / frontend / migration / etc.)
3. After reviewers report, deduplicate per the merge rules (same file:line,
   same issue → merge; conflicting severity → use higher)

The team output is **combined** with solo `code-reviewer × 3` findings AND
script results from `code_reviewer.py` and `fix_validator.py`. All three
inputs feed the unified quality report.

### Phase 5 (Fix) → `/team-debug`

When initial root-cause analysis surfaces ≥2 plausible hypotheses:

```
/team-debug "<error or file>" --hypotheses 3 --scope module
```

Mandatory pre-work:

1. Read `agent-teams/skills/parallel-debugging/SKILL.md` for the ACH framework
2. Generate hypotheses across the 6 failure-mode categories (Logic / Data /
   State / Integration / Resource / Environment) — diversify to avoid wasted
   investigation
3. After investigators report, arbitrate per the protocol (Confirmed /
   Plausible / Falsified / Inconclusive) and rank by confidence + causal
   chain strength

The chosen fix still passes `fix_validator.py` and the band-aid rejection
rules from Phase 5. **No band-aid policy exceptions regardless of how the
root cause was identified.**

### Cross-Cutting → `/team-status` and `/team-delegate`

```
/team-status [team-name]                 # snapshot members + tasks
/team-delegate [team-name]               # workload dashboard
/team-delegate <team> --rebalance        # suggest reassignments
/team-delegate <team> --assign 5=impl-3  # direct task move
/team-delegate <team> --message impl-1 'context update'
```

Use these between phases, not within. Never micromanage active investigators
or implementers — check at milestones (per
`agent-teams/skills/team-communication-protocols/SKILL.md` anti-patterns).

### Cleanup → `/team-shutdown`

```
/team-shutdown [team-name]
/team-shutdown <team> --force            # skip waiting for graceful response
/team-shutdown <team> --keep-tasks       # preserve task list
```

Every team launched must be terminated before the workflow declares Phase 8
(Ship) complete.

---

## Preset Selection Matrix

| Preset | Composition | Default Size | Best For |
|--------|-------------|--------------|----------|
| `review` | 3× team-reviewer (security, performance, architecture) | 3 | Multi-dimensional code review |
| `debug` | 3× team-debugger | 3 | Bug with multiple plausible causes |
| `feature` | 1× team-lead + 2× team-implementer | 3 | Parallel feature with shared coordination |
| `fullstack` | 1× team-lead + 1× FE + 1× BE + 1× tests | 4 | Cross-layer feature work |
| `research` | 3× general-purpose with web + codebase tools | 3 | Parallel exploration / library research |
| `security` | 4× team-reviewer (OWASP, auth, deps, secrets/config) | 4 | Comprehensive security audit |
| `migration` | 1× team-lead + 2× team-implementer + 1× team-reviewer | 4 | Large refactor / framework upgrade |

**Custom composition rule**: Only use `--custom` when no preset fits.
Custom teams require user-provided role list and risk under-defined
ownership. Prefer presets.

---

## Internal Skills Mapping

The bundled skills under `skills/` are the authoritative reference for
team operations. Load the matching skill before invoking the command.

| Command | Required Skill | Optional Skills |
|---------|----------------|-----------------|
| `/team-spawn <preset>` | `team-composition-patterns` | `task-coordination-strategies` |
| `/team-feature` | `parallel-feature-development` | `team-communication-protocols`, `task-coordination-strategies` |
| `/team-review` | `multi-reviewer-patterns` | `team-communication-protocols` |
| `/team-debug` | `parallel-debugging` | `task-coordination-strategies` |
| `/team-spawn research` | `task-coordination-strategies` | `team-communication-protocols` |
| `/team-status` | — | `team-communication-protocols` (anti-patterns) |
| `/team-delegate` | `task-coordination-strategies` | `team-communication-protocols` |
| `/team-shutdown` | `team-communication-protocols` | — |

---

## Quality Gate Preservation

**The automate-dev quality gates apply identically to team output.**

| Gate | Solo Output | Team Output |
|------|-------------|-------------|
| Breaking-change detection (`code_reviewer.py`) | HALT on detection | HALT on detection |
| Functionality preservation (100%) | Required | Required |
| Compatibility score (≥95) | Required | Required |
| Band-aid rejection (10 patterns) | Auto-reject + re-fix | Auto-reject + re-fix |
| Cyclomatic complexity (≤10/function) | Enforced | Enforced |
| Security scan (parametrised queries, no creds) | Enforced | Enforced |
| Fix validation (`fix_validator.py`) | Required | Required |
| Deployment readiness (`deployment_readiness.py`) | Required at Phase 8 | Required at Phase 8 |

Team-mode does not relax any gate. The lead synthesises team output, then
the workflow re-enters the standard Phase 3 → 7 review pipeline.

---

## Lifecycle Discipline

Every team launched must follow this sequence:

```
spawn → assign tasks → monitor → collect results → synthesise → shutdown → cleanup
```

### Spawn

Use the appropriate `/team-{spawn|feature|debug|review}` command. Verify
the pre-flight check passes (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`).

### Assign

The team-lead creates initial tasks via `TaskCreate`, sets `blockedBy`
relationships per the dependency graph, assigns owners with `TaskUpdate`.

### Monitor

Use `/team-status` periodically. Do NOT poll continuously — check at
milestones. If a teammate is idle while others are busy, run
`/team-delegate --rebalance`.

### Collect

As teammates complete tasks, gather their structured outputs:
- Reviewers → findings list
- Debuggers → hypothesis report
- Implementers → file change manifest
- Researchers → file lists + summaries

### Synthesise

Apply the matching skill's consolidation rules:
- `multi-reviewer-patterns` → deduplicate, severity-rank
- `parallel-debugging` → arbitrate hypotheses, rank by confidence
- `parallel-feature-development` → verify integration, run build/tests

### Shutdown

`/team-shutdown <team>` sends `shutdown_request` to each member, waits for
`shutdown_response`, then cleans up `~/.claude/teams/{team-name}/`.

### Failure modes

- **A teammate rejects shutdown** — They have unsaved work. Wait for the
  current task to complete, then retry (per `team-communication-protocols`).
- **A teammate is unreachable** — Check the team config; the agent may
  have completed and idled. Use `--force` only as a last resort.
- **Two teammates deadlock waiting on each other** — Lead sends a stub or
  partial result to one to unblock progress.

---

## Token Budget Adjustments

Teams scale phase costs by team size. The phase budget table from SKILL.md:

| Phase | Solo Budget | Team Budget (× team size) |
|-------|-------------|---------------------------|
| 1 Analyse | 80,000 | 80,000 × N (research preset) |
| 2 Build | 150,000 | 150,000 × N (feature/fullstack/migration) |
| 3 Review | 120,000 | 120,000 × N (review/security) |
| 5 Fix | 60,000/iter | 60,000 × N (debug) |

Track per-team usage by passing the team name as a tag to
`token_budget_monitor.py`:

```bash
python scripts/token_budget_monitor.py record <project_root> \
    --phase review --tokens 580000 --model claude-opus-4-8 \
    --tag team:review-team
```

The 90% threshold halts new parallel team launches first; existing
teammates finish their current task before the workflow escalates to user.

---

## Pre-flight Checklist

Before invoking ANY `/team-*` command:

- [ ] `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set
- [ ] `~/.claude/settings.json` has `teammateMode` configured (default `tmux`)
- [ ] The matching internal skill (`agent-teams/skills/.../SKILL.md`) has been read
- [ ] Token budget for the affected phase has headroom for `× team size`
- [ ] If a previous team is still running, `/team-status` shows it's idle
      (or run `/team-shutdown` first)
- [ ] If `--branch` is being used, working tree is clean

---

## Decision Trees

### Should this Phase escalate to a team?

```
Phase 1 (Analyse)
├── Does the task span ≥3 distinct codebase / doc / library areas?
│   ├── YES → /team-spawn research --members 3
│   └── NO  → solo: code-explorer × 2-3 (default)

Phase 2 (Build)
├── Can the work be split into ≥3 file-ownership streams with no overlap?
│   ├── YES, single-layer  → /team-feature --team-size 3
│   ├── YES, full-stack    → /team-spawn fullstack
│   ├── YES, refactor      → /team-spawn migration
│   └── NO                  → solo: code-architect × 2-3 (default)

Phase 3 / Phase 7 (Review / Validate)
├── Does the change touch auth / data / public API / UI / hot paths?
│   ├── YES, security-heavy → /team-spawn security
│   ├── YES, broad concern  → /team-review with 4-5 dimensions
│   └── NO                   → solo: code-reviewer × 3 (default)

Phase 5 (Fix)
├── Does Phase 1 analysis surface ≥2 plausible hypotheses?
│   ├── YES → /team-debug --hypotheses 3
│   └── NO  → solo root-cause analysis (default)
```

### Which preset for Mode 3?

```
What's the work?
├── Build code (parallel implementation)
│   ├── Single layer (e.g. all backend) → /team-spawn feature
│   ├── Multiple layers (FE + BE + tests) → /team-spawn fullstack
│   └── Migration / refactor → /team-spawn migration
│
├── Review code (multi-dimensional)
│   ├── Standard review → /team-review --reviewers security,performance,architecture
│   ├── Full feature → /team-review --reviewers security,performance,architecture,testing,accessibility
│   └── Security audit → /team-spawn security
│
├── Debug bug (competing hypotheses)
│   └── /team-debug --hypotheses N
│
└── Research / explore (parallel investigation)
    └── /team-spawn research --members N
```

---

## Related Documentation

- `references/agents.md` — Solo subagent definitions and orchestration patterns
- `references/feature-development.md` — Mode 2 (FD-1 to FD-7)
- `references/workflow-phases.md` — Detailed phase instructions
- `references/quality-gates.md` — Gate thresholds and pass/fail criteria
- `references/token-budgeting.md` — Cost patterns and monitoring
- `agent-teams/skills/team-composition-patterns/SKILL.md` — Sizing & preset selection
- `agent-teams/skills/parallel-feature-development/SKILL.md` — File ownership strategies
- `agent-teams/skills/multi-reviewer-patterns/SKILL.md` — Dimension allocation & dedup
- `agent-teams/skills/parallel-debugging/SKILL.md` — Analysis of Competing Hypotheses
- `agent-teams/skills/task-coordination-strategies/SKILL.md` — Decomposition & graphs
- `agent-teams/skills/team-communication-protocols/SKILL.md` — Messaging & shutdown
