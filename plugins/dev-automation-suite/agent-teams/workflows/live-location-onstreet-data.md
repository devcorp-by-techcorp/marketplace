# Workflow: Live Location On-Street Data Repeats Across Patrol Areas

## Incident Profile

Persistent issue:
- Live location street data in patrol areas such as **Drummond**, **Cardigan**,
  **Jolimont**, **East-Melbourne**, and areas outside the City of Melbourne
  often displays the same segment:

> ROSSLYN STREET  
> between Howard and king

This workflow deploys a repeatable multi-agent investigation and fix cycle using
`.agents/automate-dev/agent-teams` commands.

---

## Workflow Goal

1. Identify root cause(s) for incorrect street-segment resolution.
2. Confirm whether the fault is:
   - Geospatial zone detection,
   - Street matching/fallback logic,
   - Parking zone key normalization,
   - Caching/state reuse,
   - API payload or serializer mapping.
3. Ship a permanent fix with regression coverage for non-CBD zones.

---

## Launch Command (Debug Team)

```text
/team-debug "Live location on-street display repeats as 'ROSSLYN STREET between Howard and king' in Drummond, Cardigan, Jolimont, East-Melbourne, and non-City-of-Melbourne areas" --hypotheses 5 --scope project
```

### Required hypothesis set

Ensure investigators cover all five hypotheses:

1. **Fallback default leak** — default segment is returned when lookup misses.
2. **Coordinate projection mismatch** — lat/lng transforms push lookups toward CBD sample keys.
3. **Normalization collision** — street key canonicalization maps multiple roads to same key.
4. **Zone boundary miss** — outside-CBD points resolve to nearest/first indexed CBD block.
5. **Stale state/cache** — previous successful segment remains displayed after subsequent misses.

---

## Phase Plan

### Phase A — Reproduce and instrument

- Reproduce with location fixtures for:
  - Drummond Street corridor
  - Cardigan Street corridor
  - Jolimont / East-Melbourne corridors
  - At least two locations outside municipality
- Capture:
  - input coordinates
  - selected zone
  - selected street segment
  - fallback reason (if any)

### Phase B — Parallel evidence review

Run multi-dimensional review immediately after debug evidence:

```text
/team-review "Street resolution pipeline for live location map overlay" --dimensions security,performance,architecture,testing
```

Expected reviewer outputs:
- Architecture reviewer: resolution chain and fallback contracts.
- Testing reviewer: missing edge-case matrices (outside-zone, boundary, unknown streets).
- Performance reviewer: memoization/cache invalidation risks.
- Security reviewer: malformed payload handling (defensive parsing).

### Phase C — Parallel implementation

Once root cause is ranked high-confidence:

```text
/team-feature "Fix live location street-segment resolver so non-matching areas do not collapse to Rosslyn Street fallback; add regression tests for Drummond/Cardigan/Jolimont/East-Melbourne and non-municipality locations" --team-size 3 --plan-first
```

Decompose into 3 streams:
1. Resolver logic and fallback guardrails.
2. Geospatial/zone mapping corrections.
3. Test matrix + fixtures + assertions.

### Phase D — Validation gate

Run the repo's relevant test/lint suite and verify:
- No hard-coded fallback to Rosslyn segment.
- Unknown/out-of-zone points show explicit unknown state (or nearest valid with reasoned confidence).
- Named regression fixtures all resolve to expected streets.

Finally:

```text
/team-shutdown
```

---

## Acceptance Criteria

- Street display differs correctly by location; no global collapse to one segment.
- Drummond/Cardigan/Jolimont/East-Melbourne fixtures pass.
- Outside City of Melbourne fixtures no longer show Rosslyn unless coordinates truly map there.
- Fallback behavior is explicit, deterministic, and observable in logs/tests.

---

## Handoff Template

```markdown
## Live Location On-Street Incident — Handoff

### Root Cause
- {confirmed hypothesis}

### Code Changes
- {file}: {change summary}

### Regression Coverage
- {test name}: {scenario}

### Validation Results
- {commands + pass/fail}

### Residual Risk
- {none / details}
```
