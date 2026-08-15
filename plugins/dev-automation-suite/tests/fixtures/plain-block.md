## Pre-Output Verification

1. **Imports/dependencies resolve** — PASS: package.json updated in this change.
2. **Referenced APIs are real** — PASS: source read directly.
3. **Async operations have error handling** — FAIL: two paths in sync.ts lack a catch.
4. **No breaking changes leaked in** — PASS: git diff reviewed.
