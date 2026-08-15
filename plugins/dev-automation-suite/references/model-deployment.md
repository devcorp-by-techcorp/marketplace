# Model Deployment Strategy — Opus 4.7 Optimised

## Table of Contents

1. [Model Family Overview](#model-family-overview)
2. [Difficulty Classification](#difficulty-classification)
3. [Model Routing Matrix](#model-routing-matrix)
4. [Effort Level Configuration](#effort-level-configuration)
5. [Migration from Opus 4.6 and Earlier](#migration-from-opus-46-and-earlier)
6. [Prompt Adjustments for Opus 4.7](#prompt-adjustments-for-opus-47)

---

## Model Family Overview

The automate-dev skill is optimised for **Claude Opus 4.7** (`claude-opus-4-7`,
released 16 April 2026) as the flagship model for high-difficulty workflows,
while retaining Sonnet 4.6 for exploration and breadth-focused work.

| Model | API Identifier | Primary Use |
|-------|---------------|-------------|
| Claude Opus 4.7 | `claude-opus-4-7` | High-difficulty reasoning, review, assessment, architecture |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | Exploration, tracing, breadth-focused work |
| Claude Haiku 4.5 | `claude-haiku-4-5` | Simple classification, routing, quick validation (not used in this skill by default) |

### Opus 4.7 Capabilities Leveraged

- **1M token context window** at standard API pricing — handles large codebases
- **128k max output tokens** — sufficient for comprehensive review reports
- **xhigh effort level** (new, default in Claude Code) — between `high` and `max`
- **Adaptive thinking** — automatic reasoning depth based on task complexity
- **Prompt caching** — reduces cost on repeated SKILL.md / reference / .CLAUDE.md loads
- **Task budgets (public beta)** — enforced token spend limits for agentic loops
- **High-resolution vision** (3.75 MP) — useful for UI review with screenshots

### Opus 4.7 Pricing (as of release)

- Input: $5 per million tokens
- Output: $25 per million tokens
- Unchanged from Opus 4.6
- Note: New tokenizer produces 1.0–1.35× more tokens than Opus 4.6 for the
  same text — re-benchmark cost estimates

---

## Difficulty Classification

Every workflow task is classified by difficulty. The classification determines
model selection and effort level.

### Classification Criteria

| Level | Characteristics | Model | Effort |
|-------|----------------|-------|--------|
| **low** | Single-file reads, obvious fixes, simple lookups, formatting | sonnet | default |
| **medium** | Multi-file changes with clear scope, routine refactors, tracing | sonnet | `high` |
| **high** | Code review, architectural decisions, self-assessment, quality gates | **claude-opus-4-7** | `xhigh` |
| **xhigh** | Complex multi-file refactoring, subtle debugging, security review | **claude-opus-4-7** | `xhigh` |
| **max** | Formal verification, algorithmic proofs, cryptographic review | **claude-opus-4-7** | `max` |

### Examples by Phase

| Phase | Task | Classification | Model |
|-------|------|---------------|-------|
| 1 (Analyse) | Codebase exploration | medium | sonnet |
| 1 (Analyse) | Dependency mapping | medium | sonnet |
| 2 (Build) | Routine implementation | medium | sonnet |
| 2 (Build) | Architectural design | high | **opus-4-7** |
| 3 (Review) | Quality review (simplicity) | high | **opus-4-7** |
| 3 (Review) | Functional correctness review | high | **opus-4-7** |
| 3 (Review) | Conventions review | high | **opus-4-7** |
| 4 (Test) | Test execution | low-medium | sonnet |
| 5 (Fix) | Root cause analysis for complex bugs | high | **opus-4-7** |
| 5 (Fix) | Straightforward bug fixes | medium | sonnet |
| 6 (Simplify) | Refactoring analysis | high | **opus-4-7** |
| 7 (Validate) | Final quality gate assessment | high | **opus-4-7** |
| 7 (Validate) | Self-review of agent outputs | high | **opus-4-7** |
| 8 (Ship) | Deployment readiness check | medium | sonnet |

### Self-Review Always Uses Opus 4.7

Any workflow step involving **review of agent output** by another agent
must use Opus 4.7. This includes:

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
| code-architect | `claude-opus-4-7` | `xhigh` | high |
| code-reviewer | `claude-opus-4-7` | `xhigh` | high+ |

### Phase Routing

```
Phase 1 (Analyse):
  ├─ code-explorer × 2-3   → sonnet (parallel exploration)
  └─ dev_orchestrator.py   → script (rule-based inventory)

Phase 2 (Build):
  ├─ code-architect × 2-3  → claude-opus-4-7 xhigh (parallel design)
  └─ Implementation        → Main agent (varies by task difficulty)

Phase 3 (Review):
  ├─ code-reviewer × 3     → claude-opus-4-7 xhigh (parallel review)
  ├─ code_reviewer.py      → script (band-aid + security detection)
  └─ fix_validator.py      → script (preservation + breaking changes)

Phase 5 (Fix):
  ├─ Root cause analysis   → claude-opus-4-7 xhigh (complex bugs)
  └─ fix_validator.py      → script (band-aid detection in diffs)

Phase 6 (Simplify):
  ├─ Simplification review → claude-opus-4-7 xhigh (judgment)
  └─ code_simplifier.py    → script (structural analysis)

Phase 7 (Validate):
  ├─ code-reviewer × 3     → claude-opus-4-7 xhigh (final review)
  └─ dev_orchestrator.py   → script (full gate check)
```

---

## Effort Level Configuration

Opus 4.7 introduces `xhigh` as a new effort level between `high` and `max`.
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
/model claude-opus-4-7 --effort xhigh

# Environment variable
export ANTHROPIC_DEFAULT_EFFORT=xhigh
```

### Setting Effort via Agent Frontmatter

```yaml
---
name: code-reviewer
model: claude-opus-4-7
effort: xhigh
---
```

---

## Migration from Opus 4.6 and Earlier

If transitioning from an earlier automate-dev deployment using Opus 4.6 or
the `opus` alias, apply these changes:

### Required Changes

1. **Pin model identifier**: Replace `opus` with `claude-opus-4-7` in agent
   frontmatter to avoid alias drift
2. **Add effort level**: Set `effort: xhigh` for code-architect and code-reviewer
3. **Remove sampling parameters**: Opus 4.7 returns 400 errors for non-default
   `temperature`, `top_p`, `top_k` — remove these from any API calls
4. **Re-benchmark token budgets**: New tokenizer produces 1.0–1.35× more tokens
   — increase `max_tokens` by at least 35% headroom
5. **Update prompt caching keys**: Different tokenization means different
   cache keys for previously cached content

### Behavioural Changes to Expect

Opus 4.7 follows instructions more literally than 4.6. If your prompts
relied on inference or loose interpretation:

- **Before (4.6)**: "Review the code for issues" — model infers scope
- **After (4.7)**: "Review the code in [files] for: (1) bugs, (2) security, (3) conventions. Return top 5 issues ranked by severity with file:line references."

Opus 4.7 also spawns fewer subagents by default. If you need parallel
exploration, explicitly instruct the model:

- "Launch 3 code-explorer subagents in parallel, one for each of: [a], [b], [c]"

---

## Prompt Adjustments for Opus 4.7

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

Opus 4.7 calibrates verbosity to perceived task complexity. If you need
concise output, say so explicitly:

```
"Return a concise summary — maximum 200 words, no preamble."
```
