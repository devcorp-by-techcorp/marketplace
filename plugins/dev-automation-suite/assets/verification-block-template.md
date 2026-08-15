<!-- VENDORED ASSET — do not edit here.
     Source skill : agent-output-verification
     Source file  : assets/verification-block-template.md
     Synced       : 2026-08-11
     Amend upstream in agent-output-verification, then re-vendor.
     Tracked in CHANGELOG.md under 'Vendored assets'. -->

## Pre-Output Verification

Before presenting or delivering any code, the output must satisfy every item below. State PASS or FAIL for each item explicitly in your response, before the code itself. If any item fails, do not deliver the code — fix it first, or halt and report the specific blocker.

1. **Imports/dependencies resolve** — [PASS/FAIL]: every import and package reference exists in the project's dependency graph, or has been added to the manifest in this same change.
2. **Referenced APIs are real** — [PASS/FAIL]: every function, method, type, or class called has been confirmed to exist — not assumed from a similar-sounding pattern.
3. **Async operations have error handling** — [PASS/FAIL]: no bare await/promise without a catch path, no silent fire-and-forget async call.
4. **No breaking changes leaked in** — [PASS/FAIL]: existing function signatures, API contracts, schemas, and exported types are unchanged. If a breaking change is required by the task, it is flagged explicitly here, not silent.
5. **Existing patterns were read first** — [PASS/FAIL]: relevant existing files/modules were read before writing new code, and conventions (naming, error handling, module structure) match.
6. **Scope discipline** — [PASS/FAIL]: no unrelated refactors, renames, or incidental changes bundled in without being called out separately.

<!-- Add stack-specific items here — see references/stack-specifics.md in the agent-output-verification skill for Python/Flask, TS/Expo/RN, and Node/Express/PostgreSQL additions. -->

If ambiguity is encountered anywhere in the task, state the assumption made and proceed — do not silently guess and do not stall on trivial ambiguity. Only halt for genuine blockers (missing credentials, contradictory requirements, a required file that doesn't exist).
