# Model Deployment Strategy — Claude 5 Family

## Table of Contents

1. [Model Family Overview](#model-family-overview)
2. [Difficulty Classification](#difficulty-classification)
3. [Model Routing Matrix](#model-routing-matrix)
4. [Effort Level Configuration](#effort-level-configuration)
5. [Migration from Opus 4.x](#migration-from-opus-4x)
6. [Prompt Adjustments](#prompt-adjustments)

---

## Model Family Overview

Routing follows one rule, stated by task shape rather than by phase number:

> **Validation, conductor, and complex work → Opus 5.**
> **Report writing and discovery work → Sonnet 5 at `high` effort.**

Everything below is that rule applied to the eleven phases.

| Model | API Identifier | Primary Use |
|-------|---------------|-------------|
| Claude Opus 5 | `claude-opus-5` | Validation, orchestration, architecture, review, complex reasoning |
| Claude Sonnet 5 | `claude-sonnet-5` | Discovery, tracing, inventory, report writing |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | Simple classification and routing (not used by default) |

Agent frontmatter pins full identifiers rather than the `opus`/`sonnet`
aliases. An alias silently re-points on the next release, which changes the
behaviour of a quality gate without changing a line of this package. Pinning
means a model retirement surfaces as a launch failure — loud, and fixed by
editing three files — instead of as drift nobody attributes to the model.

Re-check identifiers against the current model list when upgrading; a pinned
identifier that is no longer served stops the agent from launching.

---

## Difficulty Classification

Every workflow task is classified by difficulty. The classification determines
model selection and effort level.

### Classification Criteria

| Level | Characteristics | Model | Effort |
|-------|----------------|-------|--------|
| **low** | Single-file reads, obvious fixes, simple lookups, formatting | `claude-sonnet-5` | default |
| **medium** | Discovery, tracing, routine refactors, report writing | `claude-sonnet-5` | `high` |
| **high** | Code review, architectural decisions, self-assessment, quality gates | **`claude-opus-5`** | `xhigh` |
| **xhigh** | Complex multi-file refactoring, subtle debugging, security review | **`claude-opus-5`** | `xhigh` |
| **max** | Formal verification, algorithmic proofs, cryptographic review | **`claude-opus-5`** | `max` |

### Examples by Phase

| Phase | Task | Classification | Model |
|-------|------|---------------|-------|
| 1 (Analyse) | Codebase exploration | medium | sonnet-5 |
| 1 (Analyse) | Dependency mapping | medium | sonnet-5 |
| 2 (Build) | Routine implementation | medium | sonnet-5 |
| 2 (Build) | Architectural design | high | **opus-5** |
| 3 (Review) | Quality review (simplicity) | high | **opus-5** |
| 3 (Review) | Functional correctness review | high | **opus-5** |
| 3 (Review) | Conventions review | high | **opus-5** |
| 4 (Test) | Test execution | low-medium | sonnet-5 |
| 5 (Fix) | Root cause analysis for complex bugs | high | **opus-5** |
| 5 (Fix) | Straightforward bug fixes | medium | sonnet-5 |
| 6 (Simplify) | Refactoring analysis | high | **opus-5** |
| 7 (Validate) | Final quality gate assessment | high | **opus-5** |
| 7 (Validate) | Self-review of agent outputs | high | **opus-5** |
| 8 (Ship) | Deployment readiness check | medium | sonnet-5 |

### Validation Always Uses Opus 5

Any workflow step involving **review of agent output** by another agent
is validation work, and must use Opus 5. This includes:

- Reviewing code written by subagents
- Validating architectural decisions produced by code-architect
- Assessing exploration output from code-explorer for gaps
- Final validation before ship
- Band-aid pattern detection in AI-generated fixes

---

## Model Routing Matrix

### Agent Configuration

| Agent | Model | Effort | Difficulty Bucket |
|-------|-------|--------|-------------------|
| code-explorer | `claude-sonnet-5` | `high` | medium — discovery |
| code-architect | `claude-opus-5` | `xhigh` | high — complex |
| code-reviewer | `claude-opus-5` | `xhigh` | high+ — validation |

### Phase Routing

```
Phase 1 (Analyse):
  ├─ code-explorer × 2-3   → claude-sonnet-5 high (parallel discovery)
  └─ dev_orchestrator.py   → script (rule-based inventory)

Phase 2 (Build):
  ├─ code-architect × 2-3  → claude-opus-5 xhigh (parallel design)
  └─ Implementation        → Main agent (varies by task difficulty)

Phase 3 (Review):
  ├─ code-reviewer × 3     → claude-opus-5 xhigh (parallel review)
  ├─ code_reviewer.py      → script (band-aid + security detection)
  └─ fix_validator.py      → script (preservation + breaking changes)

Phase 5 (Fix):
  ├─ Root cause analysis   → claude-opus-5 xhigh (complex bugs)
  └─ fix_validator.py      → script (band-aid detection in diffs)

Phase 6 (Simplify):
  ├─ Simplification review → claude-opus-5 xhigh (judgment)
  └─ code_simplifier.py    → script (structural analysis)

Phase 7 (Validate):
  ├─ code-reviewer × 3     → claude-opus-5 xhigh (final review)
  └─ dev_orchestrator.py   → script (full gate check)
```

---

## Effort Level Configuration

`xhigh` sits between `high` and `max`. Choose effort based on task complexity:

| Effort | Use For | Latency Impact | Cost Impact |
|--------|---------|---------------|-------------|
| `default` | Simple tasks, quick validation | Low | Low |
| `high` | Most coding tasks, routine review | Moderate | Moderate |
| `xhigh` | **Default for this suite's Opus 5 agents** — architectural decisions, complex debugging, deep review | High | Higher |
| `max` | Cryptographic review, formal proofs, security audits | Very high | Highest |

### Setting Effort in Claude Code

```bash
# Session-level
/effort xhigh

# Per-command (if supported)
/model claude-opus-5 --effort xhigh

# Environment variable
export ANTHROPIC_DEFAULT_EFFORT=xhigh
```

### Setting Effort via Agent Frontmatter

```yaml
---
name: code-reviewer
model: claude-opus-5
effort: xhigh
---
```

---

## Migration from Opus 4.x

Deployments pinned to `claude-opus-4-7` and the bare `sonnet` alias need three
edits, all in `agents/`:

1. `code-architect` and `code-reviewer` — `model: claude-opus-5`
2. `code-explorer` — `model: claude-sonnet-5`, `effort: high`
3. Leave `effort: xhigh` in place on the two Opus agents

Then re-benchmark token budgets. Tokenizers differ between generations, so
`references/token-budgeting.md` figures carried over from a 4.x deployment
are estimates, not measurements, until a phase has run once on the new models.
Prompt-cache keys change with tokenization too: expect the first run after a
model change to miss cache on SKILL.md and reference loads.

### Behavioural Changes to Expect

Each generation follows instructions more literally than the last. Prompts
that relied on the model inferring scope should be made explicit — the next
section covers how. Newer models also spawn fewer subagents on their own
initiative, so parallel discovery has to be asked for by name:

- "Launch 3 code-explorer subagents in parallel, one for each of: [a], [b], [c]"

---

## Prompt Adjustments

### Be Explicit About Scope

```
BAD (relies on inference):
"Check the auth module for problems"

GOOD (literal and explicit):
"Review files under app/api/v1/features/auth/ for:
1. Logic errors in token validation
2. Missing input sanitisation on login endpoint
3. Deviations from .CLAUDE.md conventions
Return findings as: file:line — severity — description"
```

### Specify Output Format

```
BAD:
"Summarise what you found"

GOOD:
"Return findings as a JSON array with fields:
- file (string)
- line (integer)
- severity (CRITICAL|HIGH|MEDIUM|LOW)
- description (string)
- suggested_fix (string)"
```

### Request Parallel Work Explicitly

```
BAD:
"Explore the codebase for similar features"

GOOD:
"Launch 3 subagents in parallel:
1. Subagent A: find features similar to [feature] in app/api/v1/features/
2. Subagent B: map architecture patterns in app/models/
3. Subagent C: identify UI conventions in app/templates/
Each subagent must return a list of 5-10 key files."
```

### Calibrate Response Length

These models calibrate verbosity to perceived task complexity. If you need
concise output, say so explicitly:

```
"Return a concise summary — maximum 200 words, no preamble."
```
