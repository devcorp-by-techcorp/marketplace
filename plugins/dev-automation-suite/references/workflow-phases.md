# Workflow Phases — Detailed Reference

## Table of Contents

1. [Phase 1: Analyse](#phase-1-analyse)
2. [Phase 2: Build](#phase-2-build)
3. [Phase 3: Review](#phase-3-review)
4. [Phase 4: Test](#phase-4-test)
5. [Phase 5: Fix](#phase-5-fix)
6. [Phase 6: Simplify](#phase-6-simplify)
7. [Phase 7: Validate](#phase-7-validate)
8. [Phase 8: Ship](#phase-8-ship)

---

## Phase 1: Analyse

### Purpose
Establish complete understanding of the existing codebase and define measurable acceptance criteria before writing any code.

### Inventory Checklist

For each target file, document:
- All public functions with signatures and return types
- All classes with their public methods and properties
- All exported constants and configuration values
- All route definitions (for web applications)
- All model definitions (for database-backed applications)
- All template references and static asset dependencies
- All inter-module dependencies (imports from project files)
- All external dependencies (third-party imports)

### Dependency Mapping

```
Target File
├── Imports From (dependencies)
│   ├── project_module_a.function_x
│   ├── project_module_b.ClassY
│   └── third_party_lib.utility_z
└── Imported By (dependents)
    ├── consuming_module_1 (uses function_a, ClassB)
    └── consuming_module_2 (uses constant_C)
```

### Acceptance Criteria Format

Each criterion must be:
- **Specific**: "User can submit the form and see a success message" not "form works"
- **Testable**: Can be verified programmatically or through defined steps
- **Independent**: Does not depend on other criteria to be verified
- **Scoped**: Relates to the specific task, not general code quality

### Iteration Plan Creation

Create `.automate-dev/iteration_plan.md` with:
- Task description and context
- Numbered acceptance criteria with checkboxes
- File targets and their dependency maps
- Initial quality baseline scores (if modifying existing code)
- Estimated complexity assessment

### Agent-Enhanced Exploration

When subagents are available, launch 2-3 **code-explorer** agents in
parallel to build deep codebase understanding before writing code.

Each agent should target a different aspect:

| Agent Focus | Example Prompt |
|-------------|----------------|
| Similar features | "Find features similar to `{feature}` and trace through their implementation comprehensively. Return 5-10 key files." |
| Architecture | "Map the architecture and abstractions for `{area}`, tracing through the code comprehensively. Return 5-10 key files." |
| Integration points | "Identify UI patterns, testing approaches, or extension points relevant to `{feature}`. Return 5-10 key files." |
| Data layer | "Trace data flow from `{entry_point}` through to `{storage}`. Return 5-10 key files." |

**After agents return:**
1. Read **all files** identified by the agents (not just the summaries)
2. Synthesise findings into a comprehensive understanding
3. Use this understanding to inform acceptance criteria and the iteration plan

See `references/agents.md` → code-explorer section for full definition and
orchestration patterns.

---

## Phase 2: Build

### Implementation Standards

#### Python / Flask
```python
# Function template
def process_item(item_id: str, config: dict) -> ProcessResult:
    """
    Process a single item according to configuration.

    Args:
        item_id: Unique identifier for the item
        config: Processing configuration parameters

    Returns:
        ProcessResult with status and output data

    Raises:
        ItemNotFoundError: When item_id does not exist
        ProcessingError: When processing fails
    """
    if not item_id:
        raise ValueError('item_id cannot be empty')

    item = Item.objects.get_or_404(id=item_id)
    # ... implementation
```

#### HTML + Tailwind CSS
```html
<!-- Semantic structure with Tailwind utilities -->
<section class="container mx-auto px-4 py-8">
    <h2 class="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Section Title
    </h2>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Content -->
    </div>
</section>
```

#### Vanilla JavaScript
```javascript
// Module pattern with explicit error handling
(function() {
    'use strict';

    async function fetchData(endpoint) {
        try {
            const response = await fetch(endpoint);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            console.error(`Failed to fetch ${endpoint}:`, error.message);
            throw error;
        }
    }

    // Expose public API
    window.ModuleName = { fetchData };
})();
```

### Delegation Patterns

#### Parallel Independent Tasks
```javascript
// Launch independent tasks simultaneously
await startAsyncSubagent({ task: 'T002', fromPlan: true });
await startAsyncSubagent({ task: 'T003', fromPlan: true });
await startAsyncSubagent({ task: 'T004', fromPlan: true });
// Collect all results
await waitForBackgroundTasks();
```

#### Sequential Dependencies
```javascript
// Task T003 depends on T002's output
const result = await subagent({ task: 'T002', fromPlan: true });
console.log(result);
// Now launch T003 with context from T002
await startAsyncSubagent({ task: 'T003', fromPlan: true });
```

### Backwards Compatibility Rules

1. **Never remove** a public function, class, method, or constant
2. **Never rename** a public symbol — add an alias if the old name is poor
3. **Never change** function signatures — add new optional parameters only
4. **Never change** return types — extend with additional fields if needed
5. **Never change** default values — unless the current default is demonstrably wrong
6. **Never change** import paths — re-export from old path if reorganising

### Agent-Enhanced Architecture Design

Before implementing complex features, launch 2-3 **code-architect** agents
with different trade-off targets:

| Approach | Agent Prompt Focus | Optimises For |
|----------|-------------------|---------------|
| Minimal | "Smallest change, maximum reuse of existing patterns" | Speed, low risk |
| Clean | "Maintainability, elegant abstractions, proper separation" | Long-term quality |
| Pragmatic | "Balance speed with quality, reasonable abstractions" | General suitability |

```javascript
await startAsyncSubagent({
    task: 'Design MINIMAL implementation for [feature]. Follow .CLAUDE.md conventions. Provide full blueprint.',
    relevantFiles: ['app/', '.CLAUDE.md']
});
await startAsyncSubagent({
    task: 'Design CLEAN ARCHITECTURE for [feature]. Provide full blueprint.',
    relevantFiles: ['app/', '.CLAUDE.md']
});
await startAsyncSubagent({
    task: 'Design PRAGMATIC BALANCE for [feature]. Provide full blueprint.',
    relevantFiles: ['app/', '.CLAUDE.md']
});
```

After agents return:
1. Compare approaches and form a recommendation
2. Present trade-offs to user with your recommendation
3. Wait for explicit approval before implementing
4. Use the approved blueprint to guide Phase 2 implementation

See `references/agents.md` → code-architect section for full definition.

---

## Phase 3: Review

### Agent-Enhanced Review

When subagents are available, launch 3 **code-reviewer** agents in parallel
alongside automated scripts for comprehensive coverage:

```javascript
// Subjective agent reviews
await startAsyncSubagent({
    task: 'Review [files] for SIMPLICITY, DRY, ELEGANCE. Top 3-5 issues by severity.',
    relevantFiles: [/* modified files */]
});
await startAsyncSubagent({
    task: 'Review [files] for BUGS, FUNCTIONAL CORRECTNESS, edge cases. Top 3-5 issues.',
    relevantFiles: [/* modified files */]
});
await startAsyncSubagent({
    task: 'Review [files] for PROJECT CONVENTIONS, ABSTRACTION quality. Top 3-5 issues.',
    relevantFiles: [/* modified files */, '.CLAUDE.md']
});

// Automated script checks (run in parallel with agents)
// python scripts/code_reviewer.py <file> --project-root <root>
// python scripts/fix_validator.py <original> <fixed> --project-root <root>
```

After all agents and scripts complete:
1. Collect all findings from agents and scripts
2. Deduplicate overlapping issues
3. Rank by severity (CRITICAL → HIGH → MEDIUM → LOW)
4. Present consolidated report to user
5. Ask: fix now, fix later, or proceed as-is

See `references/agents.md` → code-reviewer section for full definition.

### Review Checklist

#### Breaking Change Detection
- [ ] No removed public APIs
- [ ] No changed function signatures
- [ ] No changed return types
- [ ] No renamed exports
- [ ] No changed import paths
- [ ] No changed default values

#### Functionality Preservation
- [ ] All original features still work
- [ ] All original routes still respond
- [ ] All original templates still render
- [ ] All original API endpoints return same structure
- [ ] All original error handling preserved

#### Band-Aid Detection Patterns

The following patterns indicate a band-aid fix and MUST be rejected:

| Pattern | Example | Why It's a Band-Aid |
|---------|---------|-------------------|
| Exception swallowing | `except: pass` | Hides the actual problem |
| Error suppression | `try: ... except: return None` | Masks failures |
| Commented-out code | `# old_function()` as a "fix" | Dead code, not a fix |
| Hardcoded bypass | `if user_id == 'admin': skip_check()` | Doesn't address the real issue |
| Conditional skip | `if not broken_feature: run()` | Feature still broken |
| Lint suppression as fix | `# noqa` / `# type: ignore` | Suppresses, doesn't fix |
| Magic values | `timeout = 99999` to avoid timeout | Doesn't fix timeout cause |
| Retry-only fix | Adding retries without fixing root | Masks intermittent failures |

---

## Phase 4: Test

### Test Strategy Selection

| Code Type | Primary Test Method | Secondary |
|-----------|-------------------|-----------|
| API endpoints | `curl` / HTTP client | Playwright (if UI) |
| Database operations | Unit tests with fixtures | DB state verification |
| UI components | Playwright end-to-end | Visual inspection |
| Business logic | Unit tests | Integration tests |
| Background tasks | Functional tests | Log verification |

### Playwright Test Plan Template

```text
1. [New Context] Create a new browser context
2. [Browser] Navigate to /target-page
3. [Browser] Fill in form fields:
   - Field "name": "${nanoid(6)}_test"
   - Field "email": "test_${nanoid(4)}@example.com"
4. [Browser] Click "Submit" button
5. [Verify]
   - Success message is visible
   - Form data appears in results list
   - No console errors present
6. [DB] Verify record exists in database with matching data
```

---

## Phase 5: Fix

### Root Cause Analysis Process

1. **Reproduce**: Confirm the failure is consistent and understood
2. **Isolate**: Narrow down to the smallest code path that exhibits the issue
3. **Trace**: Follow data flow from input to failure point
4. **Identify**: Determine the fundamental cause (not just where it fails)
5. **Fix**: Address the root cause directly
6. **Verify**: Confirm the fix resolves the issue without side effects

### Fix Classification

| Classification | Description | Permitted? |
|---------------|-------------|-----------|
| **Structural fix** | Changes code architecture to eliminate the problem | YES |
| **Logic fix** | Corrects incorrect conditional or algorithm | YES |
| **Data fix** | Corrects data transformation or validation | YES |
| **Interface fix** | Fixes API contract adherence | YES |
| **Band-aid** | Masks symptoms without addressing cause | NO |
| **Workaround** | Bypasses the problem instead of solving it | NO |
| **Suppression** | Silences errors or warnings | NO |

---

## Phase 6: Simplify

### Simplification Targets

1. **Excessive nesting** (>3 levels) → Extract to helper functions or use early returns
2. **Duplicate logic** → Consolidate into shared utility
3. **Complex conditionals** → Extract to named boolean variables or guard clauses
4. **Long functions** (>50 lines) → Split by responsibility
5. **Unused imports** → Remove
6. **Dead code paths** → Remove
7. **Overly abstract patterns** → Flatten where abstraction adds no value

### Simplification Safety Rules

- NEVER change what the code does — only how it's structured
- ALWAYS run review checks after simplification
- NEVER combine unrelated functions "for brevity"
- ALWAYS maintain existing public API surface
- NEVER remove comments that explain non-obvious business logic

---

## Phase 7: Validate

### Validation Matrix

| Check | Threshold | Blocking? |
|-------|-----------|----------|
| Compatibility score | ≥95 | YES |
| Breaking changes | 0 | YES |
| Functionality preservation | 100% | YES |
| Band-aid patterns | 0 | YES |
| Code complexity (per fn) | ≤10 | YES (≤15 WARN) |
| Maintainability index | ≥65 | YES |
| Test pass rate | 100% | YES |

### Loop Decision Logic

```
IF all checks PASS:
    → Proceed to Phase 8 (Ship)
ELIF iteration_count >= max_iterations:
    → Escalate to user with full report
ELIF no_progress_in_last_2_iterations:
    → Escalate to user (likely stuck)
ELSE:
    → Update iteration plan
    → Return to Phase 5 with failure context
```

---

## Phase 8: Ship

### Delivery Checklist

- [ ] All quality gates pass
- [ ] Assessment report generated
- [ ] Iteration plan shows final PASS status
- [ ] No unresolved TODOs in delivered code
- [ ] All new functions have docstrings
- [ ] Error handling covers all failure paths
- [ ] Security considerations addressed
- [ ] Deployment configuration verified (if applicable)

### Assessment Report Format

```
## Automated Development Assessment
- Task: [Description]
- Iterations: N
- Final Status: PASS

### Quality Scores
- Compatibility: XX/100
- Preservation: 100%
- Code Quality: XX/100
- Band-Aid Patterns: 0

### Files Modified
- file_a.py: [Change summary]
- file_b.html: [Change summary]

### Tests Passed
- Unit: X/X
- Integration: X/X
- E2E: X/X (if applicable)
```

---

## Phase 0: Bootstrap

Runs before Analyse. Two jobs, both cheap and both preventing later rework.

1. **Stack profile detection** — `python3 scripts/stack_profile.py <root>`.
   Determines which verification items apply. Run this before any agent is
   briefed, so the correct checklist is in the brief rather than retrofitted.
2. **Budget initialisation** —
   `python3 scripts/token_budget_monitor.py init <root> --difficulty <level>`.

Also verifies package integrity: the orchestrator refuses to run when
`script_registry.missing_scripts()` is non-empty, so a packaging fault surfaces
here rather than mid-phase.

---

## Phase 8: Harden

Security pass, after the code is correct and before it ships. Separated from
Phase 3 review because hardening reasons about the system, not the diff.

**Focus**: authentication and authorization paths, input validation at trust
boundaries, secret handling, audit logging on privileged operations, dependency
vulnerabilities, destructive-operation guards.

Script: `deployment_readiness.py` covers security, error handling and
dependency checks.

Any finding on a security boundary escalates per the security escalation rule
in `references/output-verification.md`. A functional bug on a security boundary
is a security finding, and is reported at the escalated severity.

---

## Phase 9: Observe

Observability and performance. Runs after hardening so instrumentation reflects
final code paths.

**Checklist**

- Significant operations logged at appropriate levels, no secrets in log lines
- Error paths emit enough context to diagnose without reproduction
- Metrics or traces exist for new endpoints and background jobs
- No N+1 queries introduced; hot paths measured rather than assumed
- Caching applied where measurement justifies it, not pre-emptively

Performance claims made in this phase are subject to the same evidence model as
any other claim: "faster" asserted without measurement is CLAIMED, not OBSERVED.

---

## Phase 10: Ship

Delivery. Merges the original Phase 8 with the lifecycle suite's docs/release
phase.

1. Generate the assessment report
2. `python3 scripts/deployment_readiness.py <root>`
3. Confirm docs updated — README, API docs, changelog entry
4. Deliver with the assessment summary

**Delivery checklist**

- [ ] All quality gates pass, including Gate 7
- [ ] Iteration plan shows final PASS
- [ ] No unresolved TODOs in delivered code
- [ ] New public functions documented
- [ ] Error handling covers all failure paths
- [ ] Security considerations addressed and any escalations recorded
- [ ] Changelog entry written
- [ ] Deployment configuration verified
