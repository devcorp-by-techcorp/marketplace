# Model Deployment Strategy — Claude 5 Family

## Table of Contents

1. [Model Family Overview](#model-family-overview)
2. [Difficulty Classification](#difficulty-classification)
3. [Model Routing Matrix](#model-routing-matrix)
4. [Effort Level Configuration](#effort-level-configuration)
5. [Keeping Model IDs Current](#keeping-model-ids-current)
6. [Prompt Adjustments](#prompt-adjustments)

---

## Model Family Overview

The suite routes high-difficulty work to **Claude Opus 5** (`claude-opus-5`) and
breadth-focused work to **Claude Sonnet 5** (`claude-sonnet-5`).

| Model | API Identifier | Context | Primary Use |
|-------|---------------|---------|-------------|
| Claude Opus 5 | `claude-opus-5` | 1M | High-difficulty reasoning, review, assessment, architecture |
| Claude Sonnet 5 | `claude-sonnet-5` | 1M | Exploration, tracing, breadth-focused work |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | Simple classification, routing, quick validation (not used in this skill by default) |

IDs are pinned explicitly rather than using the `opus` / `sonnet` aliases, so a
run is reproducible and a model change is a reviewable diff rather than a silent
shift. That trade has a cost — see [Keeping Model IDs Current](#keeping-model-ids-current).

### Capabilities Leveraged

- **1M token context window** on both Opus 5 and Sonnet 5 — handles large codebases
- **128k max output tokens** — sufficient for comprehensive review reports
- **xhigh effort level** — between `high` and `max`; the recommended setting for
  coding and agentic work
- **Adaptive thinking** — on by default on Opus 5; reasoning depth scales with
  task complexity
- **Prompt caching** — reduces cost on repeated SKILL.md / reference / CLAUDE.md loads
- **Task budgets (beta)** — enforced token spend limits for agentic loops
- **High-resolution vision** — 2576px long edge, useful for UI review with screenshots

### Pricing

| Model | Input (per MTok) | Output (per MTok) |
|-------|-----------------|-------------------|
| Claude Opus 5 | $5 | $25 |
| Claude Sonnet 5 | $3 | $15 |
| Claude Haiku 4.5 | $1 | $5 |

Prices are Anthropic first-party API rates. Bedrock and Vertex are
partner-operated and priced separately. Verify against current published pricing
before using these figures for budgeting — this table is a snapshot, not a feed.

---

## Difficulty Classification

Every workflow task is classified by difficulty. The classification determines
model selection and effort level.

### Classification Criteria

| Level | Characteristics | Model | Effort |
|-------|----------------|-------|--------|
| **low** | Single-file reads, obvious fixes, simple lookups, formatting | sonnet | default |
| **medium** | Multi-file changes with clear scope, routine refactors, tracing | sonnet | `high` |
| **high** | Code review, architectural decisions, self-assessment, quality gates | **claude-opus-5** | `xhigh` |
| **xhigh** | Complex multi-file refactoring, subtle debugging, security review | **claude-opus-5** | `xhigh` |
| **max** | Formal verification, algorithmic proofs, cryptographic review | **claude-opus-5** | `max` |

### Examples by Phase

| Phase | Task | Classification | Model |
|-------|------|---------------|-------|
| 1 (Analyse) | Codebase exploration | medium | sonnet |
| 1 (Analyse) | Dependency mapping | medium | sonnet |
| 2 (Build) | Routine implementation | medium | sonnet |
| 2 (Build) | Architectural design | high | **opus-5** |
| 3 (Review) | Quality review (simplicity) | high | **opus-5** |
| 3 (Review) | Functional correctness review | high | **opus-5** |
| 3 (Review) | Conventions review | high | **opus-5** |
| 4 (Test) | Test execution | low-medium | sonnet |
| 5 (Fix) | Root cause analysis for complex bugs | high | **opus-5** |
| 5 (Fix) | Straightforward bug fixes | medium | sonnet |
| 6 (Simplify) | Refactoring analysis | high | **opus-5** |
| 7 (Validate) | Final quality gate assessment | high | **opus-5** |
| 7 (Validate) | Self-review of agent outputs | high | **opus-5** |
| 8 (Ship) | Deployment readiness check | medium | sonnet |

### Self-Review Always Uses Opus 5

Any workflow step involving **review of agent output** by another agent
must use Opus 5. This includes:

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
| code-explorer | `sonnet` | `high` | medium |
| code-architect | `claude-opus-5` | `xhigh` | high |
| code-reviewer | `claude-opus-5` | `xhigh` | high+ |

### Phase Routing

```
Phase 1 (Analyse):
  ├─ code-explorer × 2-3   → sonnet (parallel exploration)
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

Opus 5 introduces `xhigh` as a new effort level between `high` and `max`.
Choose effort based on task complexity:

| Effort | Use For | Latency Impact | Cost Impact |
|--------|---------|---------------|-------------|
| `default` | Simple tasks, quick validation | Low | Low |
| `high` | Most coding tasks, routine review | Moderate | Moderate |
| `xhigh` | **Default for automate-dev agents** — architectural decisions, complex debugging, deep review | High | Higher |
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

## Keeping Model IDs Current

Pinning explicit IDs buys reproducibility and pays for it in maintenance: a
pinned ID does not follow the model line forward, and nothing in the suite
fails when one goes stale. A superseded model keeps serving, so the symptom is
silent — runs simply stop getting the current generation.

The IDs live in four places. Change them together:

| Location | What to change |
|---|---|
| `agents/*.md` | the `model:` frontmatter field |
| `SKILL.md` | the agent roster and model routing tables |
| `references/model-deployment.md` | this file's overview, routing, and pricing tables |
| `scripts/token_budget_monitor.py` | `DEFAULT_MODEL` and `MODEL_PRICING` |

Keep superseded IDs in `MODEL_PRICING` when you move the default — they remain
callable, and a run that pins one should still cost out correctly.

### Migrating off a superseded pin

1. **Re-baseline token budgets** with `count_tokens` against the new model
   rather than scaling the old numbers by a fixed multiplier.
2. **Expect prompt-cache misses** on the first run: caches are model-scoped, so
   the new ID writes fresh entries.
3. **Check sampling parameters**: current models reject non-default
   `temperature`, `top_p`, and `top_k`. Steer with prompting instead.
4. **Re-check effort**: `xhigh` remains the recommendation for coding and
   agentic work, but lower levels have grown more capable — sweep `medium` and
   `high` against your own evals before assuming the old setting still fits.

### Behavioural changes to expect

Current models follow instructions more literally than the 4.x line. Prompts
that relied on the model inferring scope should state it:

- **Loose**: "Review the code for issues" — the model infers scope
- **Explicit**: "Review the code in [files] for: (1) bugs, (2) security,
  (3) conventions. Return the top 5 issues ranked by severity with file:line
  references."

Delegation behaviour also moves between generations — some models under-reach
for subagents and need encouragement, others over-reach and need a cap. Re-tune
the delegation guidance in the orchestrator prompt when you change the pin
rather than carrying the previous generation's wording forward.

---

## Prompt Adjustments for Opus 5

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

Opus 5 calibrates verbosity to perceived task complexity. If you need
concise output, say so explicitly:

```
"Return a concise summary — maximum 200 words, no preamble."
```
