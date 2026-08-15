# Breaking Change Protocols

## Definition of Breaking Changes

A breaking change is ANY modification that could cause existing code that depends on the modified code to fail or behave differently.

### Categories of Breaking Changes

#### API Breaking Changes
- Removing a public function, class, or method
- Changing function parameter names (for keyword arguments)
- Changing function parameter types
- Changing return types
- Reducing the number of accepted parameters
- Changing exception types raised

#### Behavioral Breaking Changes
- Changing default parameter values
- Changing the order of operations with side effects
- Modifying error handling behavior
- Changing validation rules
- Altering data transformation logic

#### Structural Breaking Changes
- Renaming exported symbols
- Moving code to different modules
- Changing import paths
- Modifying class inheritance hierarchy

## Detection Methodology

### Step 1: Identify Public API Surface
```
- All exported functions
- All exported classes and methods
- All exported constants
- All documented interfaces
```

### Step 2: Compare Signatures
```
For each public symbol:
  - Compare parameter count
  - Compare parameter names
  - Compare parameter types
  - Compare return types
  - Compare raised exceptions
```

### Step 3: Analyze Behavior
```
For each function:
  - Compare default values
  - Compare validation logic
  - Compare transformation logic
  - Compare side effects
```

### Step 4: Classify Changes
```
Map each detected change to severity level:
  CRITICAL | HIGH | MEDIUM | LOW
```

## User Notification Requirements

### Notification Format
```
⚠️ BREAKING CHANGE DETECTED

Change Type: [API/Behavioral/Structural]
Severity: [CRITICAL/HIGH/MEDIUM/LOW]
Location: [file:line]

Before:
  [original code/signature]

After:
  [modified code/signature]

Impact:
  - [List of affected components]
  - [Potential failure scenarios]

Required Action:
  Explicit user approval required to proceed.
```

### Notification Timing
- ALWAYS before code delivery
- NEVER after changes are made
- Include in assessment report

## Permission Acquisition Workflow

### Step 1: Present Changes
Display all breaking changes with full context

### Step 2: Request Explicit Approval
```
Do you explicitly approve the following breaking changes?
[List changes]

Please respond with:
- "yes" to approve ALL changes
- "no" to cancel and preserve original behavior
- Request specific changes to discuss individually
```

### Step 3: Document Approval
```python
# BREAKING CHANGE APPROVED
# Date: YYYY-MM-DD
# Change: [description]
# Impact: [affected components]
# User approval obtained
```

### Step 4: Proceed or Halt
- "yes" → Document and proceed
- "no" → Revert to original approach
- Specific request → Address individually

## Rollback Procedures

### If Approval Not Obtained
1. Preserve original code unchanged
2. Document the proposed changes
3. Suggest alternative approaches that avoid breaking changes
4. Request guidance on requirements

### If Issues Discovered Post-Delivery
1. Identify the breaking change
2. Prepare rollback patch
3. Document the issue
4. Apply rollback immediately
5. Re-approach with non-breaking solution
