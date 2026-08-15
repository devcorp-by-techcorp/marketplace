# Token Budgeting — Opus 4.7 Efficiency Strategies

## Table of Contents

1. [Overview](#overview)
2. [Phase-Level Budgets](#phase-level-budgets)
3. [Agent-Level Budgets](#agent-level-budgets)
4. [Prompt Caching Strategy](#prompt-caching-strategy)
5. [Task Budget Enforcement](#task-budget-enforcement)
6. [Monitoring and Alerts](#monitoring-and-alerts)
7. [Cost Optimisation Patterns](#cost-optimisation-patterns)

---

## Overview

Opus 4.7 uses a new tokenizer that produces 1.0–1.35× more tokens than
previous models. At $5/$25 per MTok, cost control matters. The automate-dev
skill applies a three-layer budgeting strategy:

1. **Phase budgets** — cap tokens per workflow phase
2. **Agent budgets** — cap tokens per agent invocation
3. **Task budgets** — cap tokens per complete workflow run (via Opus 4.7's
   task_budget feature)

### Why Budgeting Matters for Opus 4.7

- Autonomous agentic loops can burn hundreds of thousands of tokens silently
- `xhigh` effort level increases reasoning depth → more tokens
- Parallel subagent launches multiply token usage
- Iteration loops compound per cycle

---

## Phase-Level Budgets

Default token budgets per workflow phase (input + output combined):

| Phase | Default Budget | Includes | Rationale |
|-------|---------------|----------|-----------|
| 1 (Analyse) | 80,000 | 2-3 explorer agents + orchestrator | Parallel exploration |
| 2 (Build) | 150,000 | 2-3 architect agents + implementation | High-difficulty design |
| 3 (Review) | 120,000 | 3 reviewer agents + scripts | Deep multi-focus review |
| 4 (Test) | 40,000 | Test execution + log analysis | Mostly deterministic |
| 5 (Fix) | 60,000 per iteration | Root cause + fix + validation | Iterative, can recur |
| 6 (Simplify) | 40,000 | Simplification analysis | Focused scope |
| 7 (Validate) | 80,000 | 3 reviewer agents + scripts | Final quality gate |
| 8 (Ship) | 20,000 | Deployment readiness + summary | Mostly scripts |

**Default total workflow budget (1 iteration)**: ~590,000 tokens
**Default with 3 iterations in loop (Phase 5-7 repeated)**: ~950,000 tokens

### Adjusting Budgets

Budgets are configurable via `dev_orchestrator.py`:

```bash
python dev_orchestrator.py validate <project_root> \
    --targets <files> \
    --phase-budget review=150000 \
    --phase-budget fix=100000 \
    --total-budget 1500000
```

---

## Agent-Level Budgets

Per-invocation token budgets for individual agents:

| Agent | Input Budget | Output Budget | Total per Call |
|-------|-------------|---------------|----------------|
| code-explorer | 30,000 | 10,000 | 40,000 |
| code-architect | 40,000 | 20,000 | 60,000 |
| code-reviewer | 30,000 | 15,000 | 45,000 |

### Parallel Launch Cost

Launching 3 parallel agents simultaneously:

| Configuration | Cost per Run (approximate) |
|--------------|---------------------------|
| 3× code-explorer (sonnet) | 3 × 40k × $3/$15 MTok ≈ $0.45 |
| 3× code-architect (opus-4-7 xhigh) | 3 × 60k × $5/$25 MTok ≈ $1.35 |
| 3× code-reviewer (opus-4-7 xhigh) | 3 × 45k × $5/$25 MTok ≈ $1.00 |

### Respecting Budgets in Agent Prompts

Include explicit constraints in agent task descriptions:

```
"Analyse [target]. Return findings in maximum 5000 tokens.
Focus on top 5 issues only. Use concise bullet points,
no preamble. Reference file:line rather than reproducing code."
```

---

## Prompt Caching Strategy

Opus 4.7 supports prompt caching. Cache stable content to reduce cost on
repeated workflow runs.

### What to Cache

Cache breakpoints should go at the boundary of stable content:

| Content Type | Cache? | Reason |
|-------------|--------|--------|
| SKILL.md | YES | Stable across workflow runs |
| references/*.md (loaded ones) | YES | Stable per project |
| .CLAUDE.md / project conventions | YES | Rarely changes |
| .automate-dev/iteration_plan.md | NO | Updates every iteration |
| Target file contents | NO | Changes each iteration |
| Subagent outputs | NO | Per-invocation unique |

### Cache Structure Example

```python
# Pseudo-structure for a review request
messages = [
    # Cached: Project conventions (stable)
    {
        'role': 'user',
        'content': [
            {
                'type': 'text',
                'text': project_claude_md_content,
                'cache_control': {'type': 'ephemeral'}
            },
            {
                'type': 'text',
                'text': skill_context,
                'cache_control': {'type': 'ephemeral'}
            },
            # Non-cached: Dynamic content
            {
                'type': 'text',
                'text': f'Review these files: {file_contents}'
            }
        ]
    }
]
```

### Cache Savings Estimate

Prompt caching reduces input token cost by ~90% on cache hits:

- First call: 40,000 input tokens × $5/MTok = $0.20
- Subsequent calls (cache hit): 40,000 tokens × $0.50/MTok = $0.02

Across a 10-iteration workflow: ~$1.80 saved on input alone.

---

## Task Budget Enforcement

Opus 4.7 supports `task_budget` — a cap on total tokens for an entire
agentic loop. The model pauses and asks for confirmation at the limit.

### Setting Task Budgets

```python
# Via API
response = client.messages.create(
    model='claude-opus-4-7',
    task_budget={'max_tokens': 1_000_000},
    messages=[...]
)
```

```bash
# Via Claude Code
/task-budget 1000000
```

### Integration with automate-dev

The `token_budget_monitor.py` script enforces budgets outside of the
API-level task_budget by tracking usage across iterations and halting
the workflow if thresholds are breached.

```bash
# Check budget before starting iteration
python scripts/token_budget_monitor.py check <project_root>

# Record tokens used in the iteration
python scripts/token_budget_monitor.py record <project_root> \
    --phase review --tokens 45000

# View usage summary
python scripts/token_budget_monitor.py summary <project_root>
```

---

## Monitoring and Alerts

### Usage Thresholds

| Threshold | Action |
|-----------|--------|
| 50% of budget | Log warning, continue |
| 75% of budget | Log warning, notify in iteration plan |
| 90% of budget | Halt new parallel launches, serialise remaining work |
| 100% of budget | Escalate to user with full usage report |

### Running the Monitor

```bash
# At workflow start
python scripts/token_budget_monitor.py init <project_root> \
    --total-budget 1500000

# Before each phase
python scripts/token_budget_monitor.py check <project_root> \
    --phase review \
    --requested 120000

# After each phase
python scripts/token_budget_monitor.py record <project_root> \
    --phase review \
    --tokens 118000

# Generate final report
python scripts/token_budget_monitor.py report <project_root>
```

### Report Format

```json
{
    "total_budget": 1500000,
    "total_used": 847000,
    "remaining": 653000,
    "percentage_used": 56.5,
    "by_phase": {
        "analyse": {"budget": 80000, "used": 72000, "pct": 90.0},
        "build": {"budget": 150000, "used": 143000, "pct": 95.3},
        "review": {"budget": 120000, "used": 118000, "pct": 98.3},
        ...
    },
    "iterations": 2,
    "status": "ON_TRACK"
}
```

---

## Cost Optimisation Patterns

### Pattern 1: Targeted File Reading

Don't load entire directories. Read only what the agent needs:

```
BAD: relevantFiles: ['app/']  (100+ files)
GOOD: relevantFiles: ['app/api/v1/features/auth/routes.py',
                       'app/models/user.py',
                       '.CLAUDE.md']
```

### Pattern 2: Sequential Over Parallel for Dependent Work

Parallel launches are expensive. Use parallel only for truly independent
work:

```
BAD: 3 parallel agents all doing similar reviews
GOOD: 3 parallel agents with distinctly different focuses
      (simplicity, correctness, conventions)
```

### Pattern 3: Bounded Output

Instruct agents to limit output:

```
"Return the top 5 findings in maximum 2000 tokens.
Do not include full code snippets — reference file:line instead."
```

### Pattern 4: Cache Aggressively

Structure requests to maximise cache hits. Put all stable content at the
start of the message, dynamic content at the end.

### Pattern 5: Sonnet for Breadth, Opus for Depth

Use sonnet for initial exploration (breadth), then opus for deep dives
on specific findings (depth):

```
1. code-explorer (sonnet): Survey the codebase, identify 20 candidate files
2. code-reviewer (opus-4-7): Deep review of the 3 most critical files
```

### Pattern 6: Batch Reviews Across Files

When reviewing multiple files, batch them into a single agent call rather
than N separate calls:

```
BAD: 5 agent calls, one per file
GOOD: 1 agent call reviewing all 5 files, with per-file sections in output
```

### Pattern 7: Skip Agents for Low-Difficulty Work

Not every task needs an agent. For low-difficulty work, use scripts only:

```
BAD: Launch code-reviewer agent to check for bare except clauses
GOOD: Run code_reviewer.py (script) — it detects this via regex
```
