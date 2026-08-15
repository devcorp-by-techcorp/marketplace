<!-- VENDORED ASSET — do not edit here.
     Source skill : agent-output-verification
     Source file  : assets/verification-block-evidence.md
     Synced       : 2026-08-11
     Amend upstream in agent-output-verification, then re-vendor.
     Tracked in CHANGELOG.md under 'Vendored assets'. -->

## Pre-Output Verification

Before presenting or delivering any code, verify the output against every item below and report the result in the table format shown. Do not deliver code with an unresolved CONTRADICTED item, or with an UNVERIFIED item on a security-sensitive path — fix it, or halt and report the specific blocker.

**Status vocabulary** — use the one that is actually true:

- **OBSERVED** — directly established: the check was run, or the referenced code was read.
- **INFERRED** — reasonably derived from what was observed, not directly demonstrated.
- **CLAIMED** — asserted by naming, convention, comments, or your own prior statement; not established.
- **UNVERIFIED** — could not be checked. State why.
- **CONTRADICTED** — the code does something materially different from what was intended or stated.

UNVERIFIED with a stated reason is an acceptable and useful answer. CLAIMED reported as OBSERVED is not — if the basis is "a function with that name probably exists," the honest status is CLAIMED.

**Report in this form:**

| # | Check | Status | Evidence | Severity if wrong | Confidence |
|---|-------|--------|----------|-------------------|------------|
| 1 | Imports/dependencies resolve | | | | |
| 2 | Referenced APIs/types are real | | | | |
| 3 | Async operations have error handling | | | | |
| 4 | No breaking changes leaked in | | | | |
| 5 | Existing patterns read before writing | | | | |
| 6 | Scope discipline — no incidental changes | | | | |
| 7 | Delivery note matches the code produced | | | | |

<!-- Add stack-specific rows here — see references/stack-specifics.md in the agent-output-verification skill. -->

**Evidence** — name what actually supports the status, and its strength. Strongest to weakest: reproduced runtime behaviour → automated test result → source read directly → config/manifest → build/CI → version control → documentation → comments → naming convention → inference. The bottom three cannot support OBSERVED.

**Severity** (Critical / High / Medium / Low / Informational) describes the consequence if the item is wrong. **Confidence** (Very High → Very Low) describes how strong the evidence is. These are independent — `Severity: High / Confidence: Low` is a valid and useful result meaning "this would matter a lot, and I can't currently confirm it." Never raise severity because confidence is high, and never present an uncertain finding as confirmed.

**Security escalation** — if a defect touches authentication, authorization, identity, privilege boundaries, tenant or jurisdiction isolation, audit logging, input validation, sensitive or regulated data, financial transactions, or destructive operations, raise its severity accordingly and say so. A functional bug on a security boundary is a security finding.

**Row 7, self-claim reconciliation** — re-read the summary or commit message just written and compare it against the code actually produced. Any mismatch is CONTRADICTED: correct the code or correct the claim before delivering.

**Secrets** — if verification surfaces credentials, keys, or tokens, report location and type only, never the value. Treat anything found committed as potentially compromised.

**Do not report an aggregate pass rate.** Six clean items and one CONTRADICTED item on an authorization path is a blocked delivery, not a percentage.

**Limitations** — close with what constrained this verification (no runtime environment, no database access, dependency not installed, files outside the visible working set). The confidence ratings above are only interpretable against these limits.

If ambiguity is encountered in the task itself, state the assumption made and proceed — do not silently guess, and do not stall on trivial ambiguity. Halt only for genuine blockers: missing credentials, contradictory requirements, or a required file that does not exist.
