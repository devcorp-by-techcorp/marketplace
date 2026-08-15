# Quality Gates — Detailed Reference

## Table of Contents

1. [Gate Definitions](#gate-definitions)
2. [Scoring Methodology](#scoring-methodology)
3. [Pass/Fail Criteria](#passfail-criteria)
4. [Band-Aid Detection](#band-aid-detection)
5. [Deployment Readiness](#deployment-readiness)

---

## Gate Definitions

### Gate 1: Compatibility (Score 0-100)

Measures how well new/modified code integrates with the existing project.

| Factor | Weight | Measurement |
|--------|--------|-------------|
| Import compatibility | 30 | All imports resolve, no circular dependencies introduced |
| Function signature compatibility | 25 | No changes to existing signatures consumed by other modules |
| Class interface compatibility | 25 | No changes to public class APIs consumed externally |
| Integration point compatibility | 20 | Routes, templates, configs still wire correctly |

**Threshold**: ≥95 PASS | 80-94 WARN | <80 FAIL

### Gate 2: Breaking Changes (Binary)

Any detected breaking change is a blocking failure.

**Categories**:
- API removal (function, class, method, constant)
- Signature modification (parameters, return types)
- Behavioural change (different output for same input)
- Structural change (import paths, module organisation)

**Threshold**: 0 breaking changes = PASS | >0 = HALT

### Gate 3: Functionality Preservation (Percentage)

Percentage of original features/behaviours retained.

**Measurement**:
- Inventory all features in original code
- Verify each feature exists and behaves identically in modified code
- Calculate: (features_preserved / total_original_features) × 100

**Threshold**: 100% PASS | 95-99% WARN (approval needed) | <95% FAIL

### Gate 4: Code Quality (Score 0-100)

| Factor | Weight | Measurement |
|--------|--------|-------------|
| Cyclomatic complexity | 25 | Per-function complexity ≤10 target |
| Maintainability | 20 | Naming, structure, readability |
| Error handling | 20 | Specific exceptions, no bare excepts |
| Documentation | 15 | Docstrings on public APIs |
| Security | 20 | Input validation, no credential exposure |

**Threshold**: ≥80 PASS | 65-79 WARN | <65 FAIL

### Gate 5: Band-Aid Detection (Count)

Number of band-aid patterns detected in the diff between original and modified code.

**Threshold**: 0 = PASS | >0 = FAIL (automatic rejection)

### Gate 6: Test Pass Rate (Percentage)

Percentage of relevant tests passing.

**Threshold**: 100% PASS | <100% FAIL

---

## Scoring Methodology

### Compatibility Scoring

```python
def calculate_compatibility_score(analysis):
    score = 100
    
    # Import issues (-5 each, max -30)
    import_issues = analysis.get('import_issues', [])
    score -= min(len(import_issues) * 5, 30)
    
    # Signature mismatches (-10 each, max -25)
    sig_issues = analysis.get('signature_mismatches', [])
    score -= min(len(sig_issues) * 10, 25)
    
    # Class interface changes (-10 each, max -25)
    class_issues = analysis.get('class_interface_changes', [])
    score -= min(len(class_issues) * 10, 25)
    
    # Integration point breaks (-5 each, max -20)
    integration_issues = analysis.get('integration_breaks', [])
    score -= min(len(integration_issues) * 5, 20)
    
    return max(0, score)
```

### Code Quality Scoring

```python
def calculate_quality_score(analysis):
    score = 100
    
    # Complexity penalties
    for fn in analysis.get('functions', []):
        complexity = fn.get('complexity', 0)
        if complexity > 15:
            score -= 15
        elif complexity > 10:
            score -= 5
    
    # Error handling penalties
    bare_excepts = analysis.get('bare_excepts', 0)
    score -= bare_excepts * 10
    
    # Documentation coverage
    undocumented = analysis.get('undocumented_public_apis', 0)
    total_public = analysis.get('total_public_apis', 1)
    doc_coverage = (total_public - undocumented) / total_public
    if doc_coverage < 0.8:
        score -= 15
    elif doc_coverage < 1.0:
        score -= 5
    
    # Security issues
    security_issues = analysis.get('security_issues', [])
    score -= len(security_issues) * 10
    
    return max(0, score)
```

---

## Pass/Fail Criteria

### Overall Validation Decision Matrix

| Gate | Status | Blocking? | Action |
|------|--------|----------|--------|
| Compatibility ≥95 | PASS | — | Proceed |
| Compatibility 80-94 | WARN | No | Document, proceed with caution |
| Compatibility <80 | FAIL | YES | Fix before delivery |
| Breaking changes = 0 | PASS | — | Proceed |
| Breaking changes > 0 | HALT | YES | Cannot proceed without approval |
| Preservation = 100% | PASS | — | Proceed |
| Preservation 95-99% | WARN | Conditional | Requires explicit approval |
| Preservation < 95% | FAIL | YES | Must restore functionality |
| Quality ≥ 80 | PASS | — | Proceed |
| Quality 65-79 | WARN | No | Improve if possible |
| Quality < 65 | FAIL | YES | Must improve |
| Band-aids = 0 | PASS | — | Proceed |
| Band-aids > 0 | FAIL | YES | Replace with proper fixes |
| Tests 100% | PASS | — | Proceed |
| Tests < 100% | FAIL | YES | Fix failing tests |

### Overall Status Calculation

```
IF any HALT:
    overall = HALT (requires user intervention)
ELIF any FAIL:
    overall = FAIL (loop back to fix phase)
ELIF any WARN:
    overall = CONDITIONAL_PASS (proceed with documentation)
ELSE:
    overall = PASS (proceed to ship)
```

---

## Band-Aid Detection

### Detection Patterns

#### Pattern 1: Exception Swallowing
```python
# BAND-AID — swallows the error
try:
    risky_operation()
except Exception:
    pass

# PROPER FIX — handles or propagates
try:
    risky_operation()
except SpecificError as e:
    logger.error('Operation failed: %s', e)
    raise OperationFailedError('Cannot complete') from e
```

#### Pattern 2: Conditional Skip
```python
# BAND-AID — skips broken feature
if feature_flag_enabled and not known_broken:
    run_feature()

# PROPER FIX — feature works correctly
run_feature()  # Fixed the underlying issue
```

#### Pattern 3: Hardcoded Workaround
```python
# BAND-AID — hardcoded to avoid the bug
if user.id != 'problematic_user_42':
    apply_discount()

# PROPER FIX — correct discount logic for all users
apply_discount()  # Fixed the discount calculation
```

#### Pattern 4: Retry Without Fix
```python
# BAND-AID — retries mask the real issue
for attempt in range(10):
    try:
        result = flaky_operation()
        break
    except Exception:
        time.sleep(1)

# PROPER FIX — address why it's flaky
result = reliable_operation()  # Fixed connection pooling
```

#### Pattern 5: Lint/Type Suppression as Fix
```python
# BAND-AID — suppresses the warning
value = get_data()  # type: ignore[return-value]

# PROPER FIX — correct the type
value: ExpectedType = get_correctly_typed_data()
```

#### Pattern 6: Commented-Out Code as Fix
```python
# BAND-AID — "fixed" by disabling
# old_broken_function()
new_partial_workaround()

# PROPER FIX — replace with working implementation
new_correct_function()  # Replaces old_broken_function entirely
```

### Detection Algorithm

```python
BAND_AID_PATTERNS = [
    r'except\s*:\s*pass',                    # bare except with pass
    r'except\s+\w+\s*:\s*pass',              # typed except with pass
    r'except\s+.*:\s*return\s+None',         # exception returns None silently
    r'#\s*noqa',                             # lint suppression
    r'#\s*type:\s*ignore',                   # type suppression
    r'#\s*pylint:\s*disable',                # pylint suppression
    r'#\s*TODO.*workaround',                 # acknowledged workaround
    r'#\s*HACK',                             # acknowledged hack
    r'#\s*FIXME.*temporary',                 # acknowledged temporary fix
    r'timeout\s*=\s*9{3,}',                  # absurdly high timeout
    r'retry.*count\s*=\s*[5-9]\d*',          # excessive retry counts
]
```

---

## Deployment Readiness

### Pre-Deployment Checklist

| Check | Requirement |
|-------|------------|
| All quality gates | PASS or CONDITIONAL_PASS |
| Error handling | Complete — no unhandled exceptions possible |
| Logging | Significant operations logged at appropriate levels |
| Configuration | No hardcoded secrets or environment-specific values |
| Dependencies | All listed in requirements.txt / package.json |
| Database | Migrations up to date, indexes defined |
| Security | CSRF protection, input sanitisation, secure cookies |
| Performance | No N+1 queries, appropriate caching |
| Documentation | README updated, API docs current |

### Production Server Requirements

| Stack | Development Server | Production Server |
|-------|-------------------|------------------|
| Flask | `flask run` | `gunicorn --bind 0.0.0.0:5000 --reuse-port app:app` |
| Node.js | `node --watch` | `node server.js` with PM2 or equivalent |
| Static | Live server | Nginx / CDN serving from build directory |

### Deployment Verification

After deployment configuration:
1. Verify the production run command starts the application
2. Verify health check endpoint responds
3. Verify database connectivity
4. Verify static assets are served correctly
5. Verify error pages render properly

---

## Gate 7: Output Verification (Per-Item, Non-Aggregated)

Added when `agent-output-verification` was integrated. Applies to every
agent-led phase (2, 3, 5, 7).

**Mechanism**: `scripts/verification_gate.py` parses the agent's pre-output
verification block and resolves each item independently.

| Condition | Result |
|---|---|
| Any item CONTRADICTED | HALT |
| UNVERIFIED on a security-sensitive item | HALT |
| No parseable verification block on an agent-led phase | HALT |
| Aggregate pass score present in the block | HALT (block invalid) |
| OBSERVED asserted on tier 8–10 evidence | Downgrade to CLAIMED; HALT if security-sensitive, else WARN |
| Secret material present in the block | Redact, WARN, treat value as compromised |
| Missing limitations statement (evidence template) | WARN |
| UNVERIFIED with stated reason, non-security | PASS |

**Threshold**: this gate has no numeric threshold, deliberately. It produces no
score.

---

## Gate Precedence — Reconciling Numeric and Per-Item Gates

Gates 1–6 are numeric and threshold-based. Gate 7 is per-item and refuses
aggregation. Without an explicit precedence rule the integration defeats itself,
because a high compatibility score could appear to offset a contradicted
authorization check.

**The rule**: numeric gates and Gate 7 are evaluated independently, and Gate 7
is never averaged into them.

```
IF Gate 7 produces HALT:
    overall = HALT
    → no numeric score can override this
ELIF Gate 2 (breaking changes) > 0:
    overall = HALT
ELIF any numeric gate FAILs:
    overall = FAIL  → loop back to Phase 5
ELIF any gate WARNs:
    overall = CONDITIONAL_PASS  → proceed with documentation
ELSE:
    overall = PASS
```

Two consequences worth stating plainly:

1. **A perfect compatibility score does not rescue a contradicted item.** Six
   clean items and one CONTRADICTED on an authorization path is a blocked
   delivery, not 86%.
2. **Halting gates never route to Fix.** Breaking changes and Gate 7 halts
   require explicit resolution or user approval. Auto-fixing a breaking change
   is how a breaking change ships quietly.

## Halting vs Failing Checks

| Script | On failure | Rationale |
|---|---|---|
| `breaking_change_detector.py` | HALT | Breaking changes need approval, not repair attempts |
| `verification_gate.py` | HALT | Unverified delivery has no evidence to act on |
| `code_reviewer.py` | FAIL | Routed to Fix |
| `compatibility_checker.py` | FAIL | Routed to Fix |
| `functionality_preserver.py` | FAIL | Routed to Fix |
| `self_assessment.py` | FAIL / NEEDS_APPROVAL | Exit 2 means approval required |

Declared in `scripts/script_registry.py` via `halts_on_fail`, not inferred at
call sites.
