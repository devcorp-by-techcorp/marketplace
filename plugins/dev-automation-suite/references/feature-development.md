# Feature Development — Guided Workflow Reference

## Table of Contents

1. [Overview](#overview)
2. [When to Use This Workflow](#when-to-use-this-workflow)
3. [Phase FD-1: Discovery](#phase-fd-1-discovery)
4. [Phase FD-2: Codebase Exploration](#phase-fd-2-codebase-exploration)
5. [Phase FD-3: Clarifying Questions](#phase-fd-3-clarifying-questions)
6. [Phase FD-4: Architecture Design](#phase-fd-4-architecture-design)
7. [Phase FD-5: Implementation](#phase-fd-5-implementation)
8. [Phase FD-6: Quality Review](#phase-fd-6-quality-review)
9. [Phase FD-7: Summary](#phase-fd-7-summary)
10. [Integration with Core Loop](#integration-with-core-loop)

---

## Overview

The Feature Development workflow is a **guided entry mode** for the
automate-dev skill. It adds structured discovery, codebase exploration,
clarifying questions, and architecture design phases before the core
build-review-test-fix loop begins.

Use this workflow when building **new features** where understanding the
existing codebase and making architecture decisions is essential before
writing code.

### Relationship to Core Workflow

```
Feature Development Phases          Core automate-dev Phases
─────────────────────────           ──────────────────────────
FD-1: Discovery          ─┐
FD-2: Codebase Exploration │──▸  Phase 1: Analyse
FD-3: Clarifying Questions─┘
FD-4: Architecture Design ──▸  (informs Phase 2)
FD-5: Implementation      ──▸  Phase 2: Build
FD-6: Quality Review      ──▸  Phase 3: Review + Phase 4: Test
FD-7: Summary             ──▸  Phase 8: Ship
                                  ┌──────────────────────┐
                                  │ Phase 5-7 loop runs  │
                                  │ automatically after   │
                                  │ FD-6 if issues found  │
                                  └──────────────────────┘
```

After FD-6 (Quality Review), if issues are found, the standard
automate-dev loop (Fix → Simplify → Validate → loop) takes over
automatically until all quality gates pass.

---

## When to Use This Workflow

**Use Feature Development when:**
- Building a new feature from scratch
- The feature integrates with unfamiliar parts of the codebase
- Multiple implementation approaches are possible
- Architecture decisions will significantly impact maintainability
- The scope is ambiguous and needs user clarification

**Skip to core workflow (Phase 1: Analyse) when:**
- Fixing a specific bug with known location
- Making a well-defined modification to existing code
- Refactoring code where the approach is clear
- The task is simple and doesn't require codebase exploration

---

## Phase FD-1: Discovery

### Goal
Understand what needs to be built.

### Actions

1. **Create todo list** tracking all phases
2. **Parse the feature request** — extract explicit requirements, implicit
   assumptions, and open questions
3. **If the feature is unclear**, ask the user:
   - What problem are they solving?
   - What should the feature do from the user's perspective?
   - Any constraints, dependencies, or requirements?
   - Any existing patterns they want followed?
4. **Summarise understanding** and confirm with user before proceeding

### Output
Clear feature description with user confirmation that the understanding
is correct.

### Critical Rule
Do NOT proceed to codebase exploration until the feature description is
confirmed. Exploring the wrong thing wastes time.

---

## Phase FD-2: Codebase Exploration

### Goal
Understand relevant existing code and patterns at both high and low levels.

### Actions

1. **Launch 2-3 code-explorer agents in parallel**, each targeting a
   different aspect of the codebase:

   ```javascript
   // Agent 1: Similar features
   await startAsyncSubagent({
       task: 'Find features similar to [feature] and trace through their ' +
             'implementation comprehensively. Include a list of 5-10 key files to read.',
       relevantFiles: ['app/', 'src/']
   });

   // Agent 2: Architecture mapping
   await startAsyncSubagent({
       task: 'Map the architecture and abstractions for [feature area], ' +
             'tracing through the code comprehensively. Include a list of ' +
             '5-10 key files to read.',
       relevantFiles: ['app/', 'src/']
   });

   // Agent 3: Integration points
   await startAsyncSubagent({
       task: 'Identify UI patterns, testing approaches, and extension points ' +
             'relevant to [feature]. Include a list of 5-10 key files to read.',
       relevantFiles: ['app/', 'src/']
   });
   ```

2. **Once agents return**, read all files they identified to build deep
   understanding. This step is critical — the agent summaries are useful
   but reading the actual files builds the context needed for good
   architecture decisions.

3. **Present comprehensive summary** of findings and patterns discovered.

### Output
- List of discovered patterns and conventions
- Architecture diagram (mental model) of relevant code areas
- Integration points where the new feature connects
- List of files that will be modified or referenced

### Agent Prompt Templates

| Exploration Focus | Prompt Template |
|------------------|-----------------|
| Similar features | "Find features similar to `{feature}` and trace through their implementation comprehensively" |
| Architecture | "Map the architecture and abstractions for `{area}`, tracing through the code comprehensively" |
| Current state | "Analyse the current implementation of `{existing_feature}`, tracing through the code comprehensively" |
| UI patterns | "Identify UI patterns, testing approaches, or extension points relevant to `{feature}`" |
| Data layer | "Trace data flow from `{entry_point}` through transformations to `{storage}`" |
| Dependencies | "Map all internal and external dependencies for `{module_area}`" |

---

## Phase FD-3: Clarifying Questions

### Goal
Fill in all gaps and resolve every ambiguity before designing.

### CRITICAL: THIS PHASE MUST NOT BE SKIPPED

Building on assumptions leads to rework. Every minute spent clarifying
saves an hour of fixing.

### Actions

1. **Review codebase findings** from Phase FD-2 alongside the original
   feature request
2. **Identify underspecified aspects** across these categories:
   - **Edge cases**: What happens with empty inputs, invalid data, concurrent access?
   - **Error handling**: How should failures be presented to users? What should be logged?
   - **Integration points**: How does this connect to existing features? Are there conflicts?
   - **Scope boundaries**: What's explicitly NOT included in this feature?
   - **Design preferences**: Should this follow an existing pattern or establish a new one?
   - **Backward compatibility**: Will existing users, APIs, or data be affected?
   - **Performance**: Are there data volume or response time constraints?
   - **Security**: Does this handle user input, authentication, or sensitive data?
3. **Present all questions** to the user in a clear, organised list
4. **Wait for answers** before proceeding to architecture design

### Handling "Whatever you think is best"

If the user defers decisions:
1. Provide your specific recommendation for each question
2. Explain the reasoning briefly
3. Get explicit confirmation before proceeding
4. Document the decisions made

### Output
Complete list of resolved questions and decisions that form the
specification for architecture design.

---

## Phase FD-4: Architecture Design

### Goal
Design multiple implementation approaches with different trade-offs,
recommend one, and get user approval.

### Actions

1. **Launch 2-3 code-architect agents in parallel** with different focuses:

   ```javascript
   // Minimal change approach
   await startAsyncSubagent({
       task: 'Design a MINIMAL implementation for [feature] — smallest change, ' +
             'maximum reuse of existing patterns. Follow conventions in .CLAUDE.md. ' +
             'Provide complete implementation blueprint.',
       relevantFiles: ['app/', '.CLAUDE.md']
   });

   // Clean architecture approach
   await startAsyncSubagent({
       task: 'Design a CLEAN ARCHITECTURE implementation for [feature] — ' +
             'maintainability, elegant abstractions, proper separation of concerns. ' +
             'Provide complete implementation blueprint.',
       relevantFiles: ['app/', '.CLAUDE.md']
   });

   // Pragmatic balance approach
   await startAsyncSubagent({
       task: 'Design a PRAGMATIC BALANCE implementation for [feature] — ' +
             'balance speed with quality, reasonable abstractions. ' +
             'Provide complete implementation blueprint.',
       relevantFiles: ['app/', '.CLAUDE.md']
   });
   ```

2. **Review all approaches** and form your own recommendation:
   - Which fits best for this specific task?
   - Consider: small fix vs large feature, urgency, complexity, team context
   - Consider the project's established patterns (auto-discovery registry,
     blueprint-based features, MongoEngine models)

3. **Present to user**:
   - Brief summary of each approach
   - Trade-offs comparison table
   - **Your recommendation with reasoning**
   - Concrete implementation differences

4. **Ask user which approach they prefer** and wait for explicit approval

### Architecture Trade-Off Presentation Template

```
## Approach A: Minimal
- Files touched: N
- New abstractions: None
- Risk: Low
- Trade-off: May accumulate technical debt

## Approach B: Clean Architecture
- Files touched: N+M
- New abstractions: [list]
- Risk: Medium (more changes)
- Trade-off: More upfront work, easier to extend later

## Approach C: Pragmatic Balance
- Files touched: N+K (K < M)
- New abstractions: [selective list]
- Risk: Low-Medium
- Trade-off: Good middle ground

## Recommendation: Approach [X]
Reason: [specific reasoning tied to this project and task]
```

### Output
Approved architecture blueprint with:
- Files to create/modify
- Component responsibilities
- Data flow
- Build sequence
- Critical considerations (error handling, security, performance)

---

## Phase FD-5: Implementation

### Goal
Build the feature following the approved architecture.

### DO NOT START WITHOUT USER APPROVAL

### Actions

1. **Wait for explicit user approval** of the architecture
2. **Read all relevant files** identified in previous phases
3. **Create the iteration plan** (`.automate-dev/iteration_plan.md`)
4. **Implement following the chosen architecture**:
   - Follow codebase conventions strictly
   - Write clean, well-documented code
   - Use the automate-dev build standards (type hints, docstrings, error handling)
5. **For delegated tasks**, use the delegation skill:
   - Create `.local/session_plan.md` with task breakdown
   - Launch independent tasks in parallel
   - Use sequential execution for dependencies
6. **Track progress** via the iteration plan

### Output
Complete implementation ready for review.

### Transition
After implementation, the standard automate-dev workflow takes over:
- Phase 3 (Review) runs automatically
- Phase 4 (Test) runs automatically
- If issues found → Phase 5-7 loop until resolved
- Phase 8 (Ship) when all gates pass

---

## Phase FD-6: Quality Review

### Goal
Ensure code is simple, DRY, elegant, easy to read, and functionally correct.

### Actions

1. **Launch 3 code-reviewer agents in parallel** with different focuses:

   ```javascript
   // Simplicity review
   await startAsyncSubagent({
       task: 'Review [files] for SIMPLICITY, DRY principles, and ELEGANCE. ' +
             'Is the code as clean and readable as it can be? ' +
             'Identify the top 3-5 issues by severity.',
       relevantFiles: [/* modified files */]
   });

   // Correctness review
   await startAsyncSubagent({
       task: 'Review [files] for BUGS and FUNCTIONAL CORRECTNESS. ' +
             'Check logic errors, edge cases, error handling, async safety. ' +
             'Identify the top 3-5 issues by severity.',
       relevantFiles: [/* modified files */]
   });

   // Conventions review
   await startAsyncSubagent({
       task: 'Review [files] for PROJECT CONVENTIONS and ABSTRACTION quality. ' +
             'Check against .CLAUDE.md, naming, patterns, module organisation. ' +
             'Identify the top 3-5 issues by severity.',
       relevantFiles: [/* modified files */, '.CLAUDE.md']
   });
   ```

2. **Run automated scripts in parallel** with agent reviews:
   - `python scripts/code_reviewer.py` — band-aid detection, security, quality
   - `python scripts/fix_validator.py` — preservation and breaking change checks
   - `python scripts/deployment_readiness.py` — deployment verification

3. **Consolidate all findings** (agent + script):
   - Deduplicate overlapping issues
   - Rank by severity
   - Identify highest-impact issues

4. **Present findings to user** and ask:
   - Fix now (enter the automate-dev fix loop)
   - Fix later (document as known issues)
   - Proceed as-is (accept current state)

5. **Address issues** based on user decision

### Output
Quality report with all findings resolved or documented.

---

## Phase FD-7: Summary

### Goal
Document what was accomplished.

### Actions

1. **Mark all todos complete** in the iteration plan
2. **Generate assessment report** (via `dev_orchestrator.py validate`)
3. **Summarise**:
   - What was built
   - Key architecture decisions made and why
   - Files created and modified
   - Quality scores achieved
   - Suggested next steps or follow-up work

### Output
Final summary suitable for session context save.

---

## Integration with Core Loop

The feature development workflow and the core automate-dev loop are
complementary, not competing. Here is exactly how they connect:

### Entry Decision

```
User request arrives
    │
    ├── Is this a NEW FEATURE requiring codebase exploration?
    │   └── YES → Start Feature Development (FD-1 through FD-7)
    │
    ├── Is this a BUG FIX or well-defined modification?
    │   └── YES → Start Core Workflow (Phase 1: Analyse)
    │
    └── Is this a REFACTOR with clear scope?
        └── YES → Start Core Workflow (Phase 1: Analyse)
```

### Handoff Points

| Feature Dev Phase | Hands Off To | When |
|------------------|-------------|------|
| FD-5 (Implementation) complete | Phase 3 (Review) | Automatically after build |
| FD-6 (Quality Review) finds issues | Phase 5 (Fix) → loop | Automatically |
| FD-6 (Quality Review) all clear | Phase 8 (Ship) | Automatically |

### Combined Workflow Diagram

```
Feature Development Path:
  FD-1 → FD-2 → FD-3 → FD-4 → FD-5 ─┐
                                        │
Core Loop Entry:                        │
  Phase 1 → Phase 2 ──────────────────┤
                                        │
                                        ▼
                              Phase 3 (Review)
                                        │
                              Phase 4 (Test)
                                        │
                              ┌─── PASS? ───┐
                              │             │
                              NO            YES
                              │             │
                              ▼             ▼
                        Phase 5 (Fix)  Phase 8 (Ship)
                              │
                        Phase 6 (Simplify)
                              │
                        Phase 7 (Validate)
                              │
                        ┌─── PASS? ───┐
                        │             │
                        NO            YES
                        │             │
                        ▼             ▼
                   Loop back     Phase 8 (Ship)
```
