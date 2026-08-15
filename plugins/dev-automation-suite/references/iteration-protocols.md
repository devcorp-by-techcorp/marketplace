# Iteration Protocols — Detailed Reference

## Table of Contents

1. [Loop Management](#loop-management)
2. [Iteration Tracking](#iteration-tracking)
3. [Progress Detection](#progress-detection)
4. [Escalation Procedures](#escalation-procedures)
5. [Ralph-Style Autonomous Loops](#ralph-style-autonomous-loops)

---

## Loop Management

### Iteration Lifecycle

Each iteration follows a fixed sequence:

```
Iteration N
├── 1. Load previous iteration results
├── 2. Identify remaining failures
├── 3. Root cause analysis for each failure
├── 4. Apply fixes (Phase 5)
├── 5. Simplify (Phase 6)
├── 6. Validate (Phase 7)
├── 7. Record results
└── 8. Decision: PASS → Ship | FAIL → Iterate
```

### Configuration

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `max_iterations` | 10 | 1-50 | Hard cap on loop iterations |
| `min_progress_threshold` | 1 | 1-10 | Minimum score improvement per iteration |
| `stall_detection_window` | 2 | 2-5 | Consecutive iterations with no progress before escalation |
| `fix_retry_limit` | 3 | 1-5 | Max attempts at fixing a single issue before escalation |

### Iteration State Machine

```
                ┌──────────┐
                │  START   │
                └────┬─────┘
                     │
                ┌────▼─────┐
           ┌───▸│ ANALYSE  │
           │    └────┬─────┘
           │         │
           │    ┌────▼─────┐
           │    │  BUILD   │
           │    └────┬─────┘
           │         │
           │    ┌────▼─────┐
           │    │  REVIEW  │──▸ BREAKING CHANGE? ──▸ HALT
           │    └────┬─────┘
           │         │
           │    ┌────▼─────┐
           │    │   TEST   │
           │    └────┬─────┘
           │         │
           │    ┌────▼─────┐
           │    │   FIX    │
           │    └────┬─────┘
           │         │
           │    ┌────▼─────┐
           │    │ SIMPLIFY │
           │    └────┬─────┘
           │         │
           │    ┌────▼─────┐
           │    │ VALIDATE │──▸ ALL PASS? ──▸ SHIP
           │    └────┬─────┘
           │         │ FAIL
           │         │
           │    ┌────▼─────┐
           │    │ STALLED? │──▸ YES ──▸ ESCALATE
           │    └────┬─────┘
           │         │ NO
           │         │
           │    ┌────▼─────┐
           │    │ MAX ITER?│──▸ YES ──▸ ESCALATE
           │    └────┬─────┘
           │         │ NO
           └─────────┘
```

---

## Iteration Tracking

### Iteration Plan File Format

File: `.automate-dev/iteration_plan.md`

```markdown
# Iteration Plan: [Task Description]
Created: [timestamp]
Last Updated: [timestamp]

## Task Context
- **Objective**: [What we're building/fixing]
- **Target Files**: [List of files]
- **Existing Code**: [YES/NO — affects preservation requirements]

## Acceptance Criteria
- [ ] AC-1: [Specific, testable criterion]
- [ ] AC-2: [Specific, testable criterion]
- [ ] AC-3: [Specific, testable criterion]

## Baseline Scores (if modifying existing code)
- Compatibility: [score]
- Quality: [score]
- Test Coverage: [score]

---

## Iteration 1
- **Timestamp**: [ISO datetime]
- **Phase Reached**: [1-8]
- **Status**: [IN_PROGRESS | PASS | FAIL]
- **Actions Taken**:
  - [Action 1]
  - [Action 2]
- **Failures Detected**:
  - [Failure 1]: [Details]
- **Root Causes Identified**:
  - [Failure 1]: [Root cause analysis]
- **Fixes Applied**:
  - [Fix 1]: [Description — must be structural, not band-aid]
- **Quality Scores**:
  - Compatibility: [score]
  - Preservation: [percentage]
  - Quality: [score]
  - Band-Aids Detected: [count — must be 0]
- **Acceptance Criteria Progress**:
  - [x] AC-1: PASS
  - [ ] AC-2: FAIL — [reason]

---

## Iteration N
[Same structure as above]

---

## Current State
- **Active Iteration**: [N]
- **Overall Status**: [IN_PROGRESS | COMPLETE | ESCALATED]
- **Blocking Issues**: [None | List with details]
- **Progress Trend**: [IMPROVING | STALLED | REGRESSING]
```

### Score History Tracking

Maintain a running score history for stall detection:

```
Iteration | Compatibility | Preservation | Quality | Band-Aids | Tests
----------|--------------|-------------|---------|-----------|------
    1     |     72       |    100%     |   65    |     2     | 3/5
    2     |     85       |    100%     |   78    |     0     | 4/5
    3     |     95       |    100%     |   88    |     0     | 5/5
```

---

## Progress Detection

### Measurable Progress Indicators

An iteration shows progress when ANY of:
- Overall quality score increases by ≥ `min_progress_threshold`
- Number of failing tests decreases
- Number of band-aid patterns decreases
- Number of passing acceptance criteria increases
- Compatibility score increases

### Stall Detection

A stall is detected when:
- `stall_detection_window` consecutive iterations show zero progress across ALL indicators
- The same failure recurs with identical root cause across iterations
- Fixes are being reverted and re-applied cyclically

### Regression Detection

A regression occurs when:
- A previously passing test now fails
- A previously resolved issue recurs
- Quality scores decrease from previous iteration
- New breaking changes are introduced

Action on regression:
1. Immediately revert the change that caused regression
2. Re-analyse with deeper root cause investigation
3. Document the regression in the iteration plan
4. Apply a different fix strategy

---

## Escalation Procedures

### When to Escalate

| Trigger | Action |
|---------|--------|
| Max iterations reached | Present full report with all attempts |
| Stall detected (no progress) | Present blocking issue analysis |
| Fix retry limit hit for single issue | Present alternative approaches |
| Breaking change unavoidable | Request explicit approval |
| Contradictory requirements detected | Request clarification |

### Escalation Report Format

```markdown
## Development Workflow Escalation

### Summary
The automated workflow has been unable to resolve the following
issue(s) after [N] iterations.

### Blocking Issue
- **Description**: [Clear description]
- **Root Cause**: [Best understanding of root cause]
- **Attempts Made**: [Number of fix attempts]

### Fix Attempts
1. **Attempt 1**: [Strategy] → [Result] → [Why it failed]
2. **Attempt 2**: [Strategy] → [Result] → [Why it failed]
3. **Attempt 3**: [Strategy] → [Result] → [Why it failed]

### Options
1. [Option A]: [Description with trade-offs]
2. [Option B]: [Description with trade-offs]
3. [Option C]: [Manual intervention needed — specifics]

### Recommendation
[Which option and why]
```

---

## Ralph-Style Autonomous Loops

### Integration with Ralph Pattern

The automate-dev workflow can operate as a Ralph-style loop when:
- Tasks have clear, programmatically verifiable completion criteria
- No human judgment is required during execution
- Automated tests serve as the completion oracle

### Autonomous Loop Structure

```
WHILE (iteration < max_iterations AND NOT all_gates_pass):
    IF iteration == 1:
        run_phase_1_analyse()
        run_phase_2_build()
    
    run_phase_3_review()
    run_phase_4_test()
    
    IF has_failures:
        run_phase_5_fix(failures)
        run_phase_6_simplify()
    
    results = run_phase_7_validate()
    update_iteration_plan(results)
    
    IF is_stalled(results):
        escalate_to_user()
        BREAK
    
    iteration += 1

IF all_gates_pass:
    run_phase_8_ship()
ELSE:
    generate_escalation_report()
```

### Completion Verification

Completion is verified when ALL of:
1. Every acceptance criterion is checked off
2. All quality gate thresholds are met
3. Zero band-aid patterns detected
4. Zero breaking changes present
5. 100% functionality preservation confirmed
6. All tests pass

### Safety Mechanisms

- **Hard iteration cap**: Prevents infinite loops
- **Stall detection**: Catches unproductive cycling
- **Regression detection**: Catches backwards movement
- **Breaking change halt**: Stops before causing damage
- **Band-aid rejection**: Forces proper fixes
- **User escalation**: Defers to human judgment when stuck
