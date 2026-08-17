# Agents — Specialised Subagent Definitions

## Table of Contents

1. [Agent Overview](#agent-overview)
2. [code-explorer Agent](#code-explorer-agent)
3. [code-architect Agent](#code-architect-agent)
4. [code-reviewer Agent](#code-reviewer-agent)
5. [Agent Orchestration Patterns](#agent-orchestration-patterns)
6. [Team Agents (Mode 3)](#team-agents-mode-3)

---

## Agent Overview

The automate-dev workflow uses two complementary agent families:

1. **Solo subagents** (this section, primary focus) — three specialised types
   launched via the `delegation` skill (`subagent`, `startAsyncSubagent`) or
   the `architect` function from the `code_review` skill. Used in Modes 1 & 2.
2. **Team agents** (see [Team Agents](#team-agents-mode-3) below) — four
   coordinated types launched as a managed team via `/team-*` slash commands.
   Used in Mode 3 for parallel multi-stream work.

Each solo agent has a distinct responsibility and is optimised for a specific
phase of the development loop.

### Agent Definition Files

The agent persona definitions live in `agents/` and must be installed to
`.claude/agents/` in your project for Claude Code to use them:

| File | Install To |
|------|-----------|
| `agents/code-explorer.md` | `.claude/agents/code-explorer.md` |
| `agents/code-architect.md` | `.claude/agents/code-architect.md` |
| `agents/code-reviewer.md` | `.claude/agents/code-reviewer.md` |

Without these files installed, subagents still function but run as generic
agents without the specialised persona, model assignment, or tool constraints.

### Agent Summary

| Agent | Primary Phase | Responsibility | Model | Effort | Colour |
|-------|--------------|----------------|-------|--------|--------|
| code-explorer | 1 (Analyse) | Deep codebase tracing and pattern discovery | `sonnet` | high | yellow |
| code-architect | 2 (Build) | Architecture design and implementation blueprints | `claude-opus-4-8` | xhigh | green |
| code-reviewer | 3 (Review), 7 (Validate) | Quality review — simplicity, correctness, conventions | `claude-opus-4-8` | xhigh | red |

**Model rationale** (see `references/model-deployment.md` for full strategy):

- **code-explorer** uses sonnet — exploration is breadth-focused (medium
  difficulty); sonnet is fast and cost-effective for tracing and pattern
  discovery across many files.
- **code-architect** uses Opus 4.8 with `xhigh` effort — architectural
  decisions fit Anthropic's `xhigh` use case (complex multi-file decisions,
  high difficulty) and benefit from deeper reasoning.
- **code-reviewer** uses Opus 4.8 with `xhigh` effort — reviewing agent
  output is self-assessment territory; quality judgment, linting, and
  conventions review are classified as high+ difficulty.

### Available Tools (All Agents)

All agents have access to: `Glob`, `Grep`, `LS`, `Read`, `NotebookRead`,
`WebFetch`, `TodoWrite`, `WebSearch`, `KillShell`, `BashOutput`

### When to Use Agents vs Scripts

| Situation | Use Agent | Use Script |
|-----------|-----------|------------|
| Deep codebase understanding before building | code-explorer | — |
| Architecture decisions for new features | code-architect | — |
| Subjective code quality review | code-reviewer | — |
| Automated band-aid detection | — | `code_reviewer.py` |
| Breaking change detection | — | `code_reviewer.py` |
| Fix validation | — | `fix_validator.py` |
| Deployment readiness | — | `deployment_readiness.py` |
| Parallel analysis of multiple concerns | 2-3 agents | — |

Agents handle judgment-intensive analysis. Scripts handle rule-based checks.
Use both together for comprehensive coverage.

---

## code-explorer Agent

### Identity

Expert code analyst specialising in tracing and understanding feature
implementations across codebases.

### Core Mission

Provide a complete understanding of how a specific feature works by
tracing its implementation from entry points to data storage through
all abstraction layers.

### Analysis Approach

**1. Feature Discovery**
- Find entry points (APIs, UI components, CLI commands)
- Locate core implementation files
- Map feature boundaries and configuration

**2. Code Flow Tracing**
- Follow call chains from entry to output
- Trace data transformations at each step
- Identify all dependencies and integrations
- Document state changes and side effects

**3. Architecture Analysis**
- Map abstraction layers (presentation → business logic → data)
- Identify design patterns and architectural decisions
- Document interfaces between components
- Note cross-cutting concerns (auth, logging, caching)

**4. Implementation Details**
- Key algorithms and data structures
- Error handling and edge cases
- Performance considerations
- Technical debt or improvement areas

### Output Requirements

The agent must produce:
- Entry points with `file:line` references
- Step-by-step execution flow with data transformations
- Key components and their responsibilities
- Architecture insights: patterns, layers, design decisions
- Dependencies (external and internal)
- Observations about strengths, issues, or opportunities
- **List of 5-10 essential files** for understanding the topic

### Usage Patterns

**Launch for codebase discovery (Phase 1):**
```javascript
// Parallel exploration of different aspects
await startAsyncSubagent({
    task: 'Find features similar to [target feature] and trace their implementation comprehensively. Return a list of the 5-10 most important files.',
    relevantFiles: ['src/', 'app/']
});

await startAsyncSubagent({
    task: 'Map the architecture and abstractions for [feature area], tracing through the code comprehensively. Return a list of the 5-10 most important files.',
    relevantFiles: ['src/', 'app/']
});

await startAsyncSubagent({
    task: 'Analyse the current implementation of [existing feature], tracing through the code comprehensively. Return a list of the 5-10 most important files.',
    relevantFiles: ['src/', 'app/']
});
```

**Launch for targeted investigation:**
```javascript
const result = await subagent({
    task: 'Trace the complete execution path of the user authentication flow from login form submission to session creation. Include every file touched.',
    relevantFiles: ['app/api/v1/features/auth/', 'app/models/']
});
console.log(result);
```

### Example Prompts

| Context | Prompt |
|---------|--------|
| Similar features | "Find features similar to [feature] and trace through their implementation comprehensively" |
| Architecture mapping | "Map the architecture and abstractions for [area], tracing through the code comprehensively" |
| Existing analysis | "Analyse the current implementation of [feature], tracing through the code comprehensively" |
| UI patterns | "Identify UI patterns, testing approaches, or extension points relevant to [feature]" |
| Data flow | "Trace data flow from API endpoint `/api/users` through to MongoDB persistence" |

---

## code-architect Agent

### Identity

Senior software architect who delivers comprehensive, actionable architecture
blueprints by deeply understanding codebases and making confident
architectural decisions.

### Core Process

**1. Codebase Pattern Analysis**
- Extract existing patterns, conventions, and architectural decisions
- Identify the technology stack, module boundaries, abstraction layers
- Find `.CLAUDE.md` guidelines and project conventions
- Locate similar features to understand established approaches

**2. Architecture Design**
- Based on patterns found, design the complete feature architecture
- Make decisive choices — pick one approach and commit
- Ensure seamless integration with existing code
- Design for testability, performance, and maintainability

**3. Complete Implementation Blueprint**
- Specify every file to create or modify
- Define component responsibilities
- Map integration points
- Chart data flow
- Break implementation into clear phases with specific tasks

### Output Requirements

The agent must produce:
- **Patterns & Conventions Found**: Existing patterns with `file:line` references, similar features, key abstractions
- **Architecture Decision**: Chosen approach with rationale and trade-offs
- **Component Design**: Each component with file path, responsibilities, dependencies, and interfaces
- **Implementation Map**: Specific files to create/modify with detailed change descriptions
- **Data Flow**: Complete flow from entry points through transformations to outputs
- **Build Sequence**: Phased implementation steps as a checklist
- **Critical Details**: Error handling, state management, testing, performance, and security considerations

### Usage Patterns

**Launch for architecture design (Phase 2):**
```javascript
// Parallel architecture exploration with different trade-offs
await startAsyncSubagent({
    task: 'Design a MINIMAL implementation for [feature] — smallest change, maximum reuse of existing patterns. Follow conventions in .CLAUDE.md.',
    relevantFiles: ['app/', '.CLAUDE.md']
});

await startAsyncSubagent({
    task: 'Design a CLEAN ARCHITECTURE implementation for [feature] — maintainability, elegant abstractions, proper separation of concerns.',
    relevantFiles: ['app/', '.CLAUDE.md']
});

await startAsyncSubagent({
    task: 'Design a PRAGMATIC BALANCE implementation for [feature] — balance speed with quality, reasonable abstractions.',
    relevantFiles: ['app/', '.CLAUDE.md']
});
```

**Launch for single decisive design:**
```javascript
const result = await subagent({
    task: 'Design the complete architecture for [feature]. Make decisive choices — pick one approach and commit. Provide a full implementation blueprint.',
    relevantFiles: ['app/api/v1/features/', 'app/models/', '.CLAUDE.md']
});
console.log(result);
```

### Architecture Trade-Off Matrix

When launching multiple architect agents, each should target a different
quadrant:

| Approach | Optimises For | Sacrifices | Best When |
|----------|--------------|------------|-----------|
| Minimal | Speed, low risk | Long-term elegance | Small fixes, urgent work |
| Clean | Maintainability | Implementation time | Large features, team code |
| Pragmatic | Balance | Neither extreme | Most general work |

---

## code-reviewer Agent

### Identity

Expert code reviewer focused on quality, correctness, and alignment with
project standards. Provides subjective judgment that complements the
automated script-based checks.

### Review Responsibilities

Three specialised focus areas — launch one agent per focus:

**1. Simplicity / DRY / Elegance**
- Is the code as simple as it can be?
- Is there duplicated logic that should be consolidated?
- Are abstractions appropriate (not too many, not too few)?
- Is the code easy to read and understand?
- Could any function be split or combined for clarity?

**2. Bugs / Functional Correctness**
- Are there logic errors or off-by-one mistakes?
- Are edge cases handled (empty inputs, null values, boundaries)?
- Is error handling correct and complete?
- Do async operations handle failures properly?
- Are race conditions possible?

**3. Project Conventions / Abstractions**
- Does the code follow `.CLAUDE.md` and project conventions?
- Are naming conventions consistent with the codebase?
- Are the right abstractions used (existing patterns vs new ones)?
- Is the code organised like similar features in the project?
- Are imports, file structure, and module boundaries correct?

### Usage Patterns

**Launch for quality review (Phase 3 / Phase 7):**
```javascript
// Parallel review with different focuses
await startAsyncSubagent({
    task: 'Review [files] for SIMPLICITY, DRY principles, and ELEGANCE. Is the code as clean and readable as it can be? Identify the top 3-5 issues.',
    relevantFiles: ['path/to/modified/files']
});

await startAsyncSubagent({
    task: 'Review [files] for BUGS and FUNCTIONAL CORRECTNESS. Check logic errors, edge cases, error handling, and async safety. Identify the top 3-5 issues.',
    relevantFiles: ['path/to/modified/files']
});

await startAsyncSubagent({
    task: 'Review [files] for PROJECT CONVENTIONS and ABSTRACTION quality. Check against .CLAUDE.md, naming, patterns, and module organisation. Identify the top 3-5 issues.',
    relevantFiles: ['path/to/modified/files', '.CLAUDE.md']
});
```

### Consolidating Review Findings

After all review agents return:
1. Collect all findings
2. Deduplicate overlapping issues
3. Rank by severity (CRITICAL → HIGH → MEDIUM → LOW)
4. Present top issues with recommended actions
5. Ask user whether to fix now, fix later, or proceed as-is

---

## Agent Orchestration Patterns

### Pattern 1: Parallel Exploration (Phase 1)

Launch 2-3 code-explorer agents simultaneously, each targeting a different
aspect of the codebase. Collect results, read all identified files, then
synthesise findings.

```javascript
// Launch in parallel
await startAsyncSubagent({ task: 'Explore [aspect A]...', relevantFiles: [...] });
await startAsyncSubagent({ task: 'Explore [aspect B]...', relevantFiles: [...] });
await startAsyncSubagent({ task: 'Explore [aspect C]...', relevantFiles: [...] });

// Collect results
await waitForBackgroundTasks();

// Read all files identified by agents
// Synthesise comprehensive understanding
```

### Pattern 2: Competitive Architecture (Phase 2)

Launch 2-3 code-architect agents with different trade-off targets. Compare
outputs, form a recommendation, present to user for decision.

```javascript
await startAsyncSubagent({ task: 'Design MINIMAL approach...', relevantFiles: [...] });
await startAsyncSubagent({ task: 'Design CLEAN approach...', relevantFiles: [...] });
await startAsyncSubagent({ task: 'Design PRAGMATIC approach...', relevantFiles: [...] });

await waitForBackgroundTasks();

// Compare approaches
// Form recommendation
// Present to user
```

### Pattern 3: Multi-Focus Review (Phase 3 / 7)

Launch 3 code-reviewer agents, each with a different quality focus.
Consolidate findings, rank by severity, present actionable list.

```javascript
await startAsyncSubagent({ task: 'Review for SIMPLICITY...', relevantFiles: [...] });
await startAsyncSubagent({ task: 'Review for CORRECTNESS...', relevantFiles: [...] });
await startAsyncSubagent({ task: 'Review for CONVENTIONS...', relevantFiles: [...] });

await waitForBackgroundTasks();

// Consolidate, deduplicate, rank
// Present top issues to user
```

### Pattern 4: Sequential Deep Dive

When a specific issue needs focused investigation, use synchronous agents:

```javascript
// First understand the problem
const exploration = await subagent({
    task: 'Trace the auth flow and identify where session validation fails...',
    relevantFiles: ['src/auth/']
});
console.log(exploration);

// Then design the fix
const design = await subagent({
    task: `Based on this analysis: ${exploration.result}\nDesign a fix that...`,
    relevantFiles: ['src/auth/']
});
console.log(design);
```

### Pattern 5: Agent + Script Combination

Use agents for judgment, scripts for rules. Run both during review:

```javascript
// Agent: subjective quality review
await startAsyncSubagent({
    task: 'Review modified files for simplicity and correctness...',
    relevantFiles: [...]
});

// Script: automated rule checks (run in parallel)
// python scripts/code_reviewer.py <file> --project-root <root>
// python scripts/fix_validator.py <original> <fixed> --project-root <root>

await waitForBackgroundTasks();

// Combine agent findings with script results
// Present unified quality report
```

### Pattern 6: Solo + Team Combination (Mode 3)

For complex work, run solo agents AND a team in parallel. Solo agents
provide cross-cutting subjective judgment while the team provides
parallel breadth on dimension-specific concerns.

```
# Phase 3 (Review) — comprehensive quality assessment
1. Solo: code-reviewer × 3 (simplicity / correctness / conventions)
2. Team: /team-review --reviewers security,performance,accessibility,testing
3. Scripts: code_reviewer.py + fix_validator.py
4. Synthesise: deduplicate per multi-reviewer-patterns/SKILL.md
```

The deduplication rules merge solo and team findings at the same
`file:line` and apply the higher severity if they conflict.

---

## Team Agents (Mode 3)

When the workflow escalates to Mode 3 (Team Coordination), four additional
agent personas are launched as a managed team via `/team-*` slash commands.
Definitions live in `agent-teams/agents/`.

### Team Agent Definition Files

Install to `.claude/agents/` alongside the solo agents:

| File | Install To |
|------|-----------|
| `agent-teams/agents/team-lead.md` | `.claude/agents/team-lead.md` |
| `agent-teams/agents/team-implementer.md` | `.claude/agents/team-implementer.md` |
| `agent-teams/agents/team-reviewer.md` | `.claude/agents/team-reviewer.md` |
| `agent-teams/agents/team-debugger.md` | `.claude/agents/team-debugger.md` |

### Team Agent Summary

| Agent | Colour | Model | Role | Primary Command |
|-------|--------|-------|------|-----------------|
| **team-lead** | blue | claude-opus-4-8 | Decompose work, assign file ownership, monitor, synthesise | All `/team-*` (orchestration role) |
| **team-implementer** | yellow | claude-opus-4-8 | Build within strict file-ownership boundaries; coordinate at integration points | `/team-feature`, `/team-spawn fullstack/migration` |
| **team-reviewer** | green | claude-opus-4-8 | Single-dimension review (security / perf / arch / testing / a11y) | `/team-review`, `/team-spawn security` |
| **team-debugger** | red | claude-opus-4-8 | Hypothesis-driven investigation with confidence ratings | `/team-debug` |

### When to Use Team Agents vs Solo Subagents

| Situation | Use Solo | Use Team |
|-----------|----------|----------|
| Single-file change | code-reviewer × 3 | — |
| ≥3 file-ownership streams | — | `/team-feature` (lead + implementers) |
| Standard 3-dimension review (simplicity/correctness/conventions) | code-reviewer × 3 | — |
| 4-5 dimension review with security focus | — | `/team-review` |
| Single-cause bug investigation | code-explorer + manual analysis | — |
| Multi-cause bug requiring competing hypotheses | — | `/team-debug` |
| Architecture for known feature | code-architect × 2-3 | — |
| Cross-layer feature (FE + BE + tests + infra) | — | `/team-spawn fullstack` |
| Codebase migration | — | `/team-spawn migration` |
| Comprehensive security audit | — | `/team-spawn security` |
| Parallel codebase + library + doc research | — | `/team-spawn research` |

### Team Lifecycle (mandatory for every spawn)

```
spawn → assign tasks → monitor → collect → synthesise → shutdown → cleanup
```

Every team launched via Mode 3 must terminate via `/team-shutdown` before
the workflow declares Phase 8 (Ship) complete. See
`references/agent-teams-integration.md` for the full lifecycle specification
and pre-flight checklist.

### Team Agent Constraints

The team agents enforce internal constraints that the workflow relies on:

- **team-lead**: One owner per file (Cardinal Rule); never assigns vague or
  overlapping tasks; uses TaskUpdate for status (never structured JSON
  messages); refers to teammates by NAME, never UUID.
- **team-implementer**: Never modifies unassigned files; references
  interface contracts but never mutates them; reports blockers immediately
  rather than working around them.
- **team-reviewer**: Stays strictly within assigned dimension; cites
  `file:line` for every finding; rates severity evidence-based, not
  opinion-based; honestly reports "no findings".
- **team-debugger**: Reports both confirming AND contradicting evidence;
  scopes claims to what was actually verified; stays focused on assigned
  hypothesis even when other leads emerge (reports tangents, doesn't chase).

These constraints are enforced by the agent definitions themselves; the
workflow does not need to re-state them in task descriptions.

### Internal Skills That Govern Team Behaviour

When operating in Mode 3, load the matching internal skill from `skills/`
before invoking the command. These skills define how the team agents
should be coordinated:

| Skill (in `agent-teams/skills/`) | Governs |
|---------------------|---------|
| `team-composition-patterns/SKILL.md` | Team sizing, preset selection, agent-type selection |
| `parallel-feature-development/SKILL.md` | File ownership strategies, conflict avoidance, integration patterns |
| `multi-reviewer-patterns/SKILL.md` | Review-dimension allocation, finding deduplication, severity calibration |
| `parallel-debugging/SKILL.md` | Hypothesis generation, evidence standards, confidence levels, arbitration |
| `task-coordination-strategies/SKILL.md` | Task decomposition, dependency graphs, workload monitoring |
| `team-communication-protocols/SKILL.md` | Message-type selection, plan approval, shutdown procedures |

See `references/agent-teams-integration.md` for the full command-by-phase
mapping, decision trees, and quality-gate preservation rules.
