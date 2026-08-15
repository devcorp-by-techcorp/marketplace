# Agent Roster

## Core agents (bundled)

| Agent | Role | Model | Effort | Colour | Phases |
|---|---|---|---|---|---|
| `code-explorer` | Codebase tracing, pattern discovery | `sonnet` | high | yellow | 1 |
| `code-architect` | Architecture design, implementation blueprints | `claude-opus-5` | xhigh | green | 2 |
| `code-reviewer` | Quality review — simplicity, correctness, conventions | `claude-opus-5` | xhigh | red | 3, 7 |

**Routing rationale**

- `code-explorer` uses Sonnet: exploration is breadth-focused (medium
  difficulty), and Sonnet is fast and cost-effective for tracing across many
  files.
- `code-architect` uses Opus 5 at `xhigh`: architectural decisions are complex
  multi-file judgments that benefit from deeper reasoning.
- `code-reviewer` uses Opus 5 at `xhigh`: reviewing another agent's output is
  self-assessment territory, classified high difficulty or above.

All three carry `## Exit Criteria — Pre-Output Verification`. That section is
the contract the `SubagentStop` hook enforces.

## Orchestration patterns

**Phase 1 — parallel exploration.** Launch 2–3 `code-explorer` agents on
different aspects (similar features, architecture, integration points, data
layer). Read every file they identify, not just their summaries.

**Phase 2 — competing architectures.** Launch 2–3 `code-architect` agents with
different trade-off targets: minimal (smallest change, maximum reuse), clean
(maintainability, proper separation), pragmatic (balance). Compare, recommend,
wait for explicit approval before implementing.

**Phase 3/7 — parallel review.** Launch 3 `code-reviewer` agents with distinct
focuses: simplicity/DRY/elegance, bugs/correctness, conventions/abstractions.
Consolidate with script findings, deduplicate, rank by severity.

Agents provide judgment. Scripts provide rule enforcement. Neither substitutes
for the other:

```
Phase 3 (Review)
├── Agent: code-reviewer (simplicity)    ─┐
├── Agent: code-reviewer (correctness)    │──▸ consolidated report
├── Agent: code-reviewer (conventions)   ─┘
├── Script: code_reviewer.py             (band-aids, security, breaking changes)
├── Script: breaking_change_detector.py  (HALTS on detection)
├── Script: compatibility_checker.py
├── Script: functionality_preserver.py
└── Gate:   verification_gate.py         (per-item, HALTS)
```

## Onboarding an external agent into the gate

The wider ecosystem holds many more agent definitions — backend-architect,
security-auditor, test-automator, mobile-developer and others across plugin
directories. Any of them that produces code must pass the same gate.

To onboard one:

1. Append the `## Exit Criteria — Pre-Output Verification` block from any core
   agent to the agent definition. Do not paraphrase it — the gate parses what
   the block produces, and reworded instructions produce unparseable output.
2. Tailor the stack-specific items using
   `python3 scripts/stack_profile.py <root> --checklist`. Don't paste
   Python-specific items into a React Native agent's brief.
3. Reference the calling workflow's phase gates rather than restating them.
   Duplicated gate definitions drift.
4. Verify by piping a sample output through the hook:

   ```bash
   python3 -c "import json,sys;print(json.dumps({'output':sys.stdin.read()}))" < sample.md \
     | bash hooks/subagent-verification-gate.sh
   ```

**Duplication caution.** Agent names recur across plugin directories —
`code-reviewer` and `backend-architect` each appear in several. Copies drift.
Before onboarding, diff the variants and decide which is authoritative; wiring
the gate into a stale copy gives the appearance of coverage without the effect.

## Model routing for onboarded agents

Apply the difficulty table in `references/model-deployment.md`. The rule that
matters most: **any agent reviewing work produced by another agent runs on Opus
4.7 at `xhigh`**. Self-assessment on a weaker model is where false passes enter.
