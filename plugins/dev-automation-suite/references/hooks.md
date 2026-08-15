# Hook Wiring

## SubagentStop — the verification gate

`hooks/subagent-verification-gate.sh` is the enforcement point. Registered for
all subagents via `hooks/hooks.json`.

**Flow**: agent finishes → hook reads payload → extracts the verification block
→ delegates to `scripts/verification_gate.py` → emits an approve/block decision.

**Payload handling.** Accepts JSON (`output`, `response`, `text`, `content`,
`message`, `result` keys, including content-block list form) and raw text. The
full payload is read; nothing is truncated. Agent output legitimately contains
colons, pipes, and newlines.

**Decision object**:

```json
{ "decision": "block", "reason": "Blocked by verification gate — see per-item report",
  "report": "…full per-item output…" }
```

No `scores` object and no aggregate value, by design.

**Exit behaviour.** The hook always exits 0; the decision travels in the payload
so a tooling problem never silently blocks legitimate work. Gate exit codes:
`0` approved · `1` blocked · `2` approved with warnings · `3` no parseable block.

Exit 3 blocks: an agent that produced code without a parseable block has given
the gate no evidence to act on.

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `CLAUDE_PLUGIN_ROOT` | Suite root, used to resolve the gate script | derived from hook path |
| `CLAUDE_PROJECT_DIR` | Log destination root | `$PWD` |
| `CLAUDE_SESSION_ID` | Log filename discriminator | UTC timestamp |
| `PYTHON_BIN` | Python interpreter | `python3` |

Logs: `${CLAUDE_PROJECT_DIR}/.dev-suite/logs/subagent_gate_<session>.log`

## What this replaced, and why

The predecessor `subagent-quality-gate.sh` had a design flaw and four defects.
They are recorded here because the same mistakes are easy to reintroduce.

**Design flaw** — it evaluated the agent's *prose*, not the code. It grepped for
the word "try" to conclude error handling existed, and counted `{` characters as
nesting depth. It then collapsed everything into
`(completeness×40 + safety×40 + clarity×20)/100`, so a critical safety failure
could be offset by verbose, comment-rich prose.

**Defects**

1. `cut -d: -f2-` truncated agent output at the first colon.
2. Issue collection used `<<< "$a$b$c"` with no newlines between evaluator
   outputs, silently dropping issues from the 2nd and 3rd.
3. `grep -ci … || echo 0` under `set -euo pipefail` could emit multi-line output
   into an arithmetic comparison.
4. Matched credential text was echoed into the report unredacted.

All four are covered by regression tests in `tests/test_suite.py::TestHook`.

## Testing a hook change

```bash
python3 tests/test_suite.py -k TestHook

# Manual single case
python3 -c "import json;print(json.dumps({'output':open('tests/fixtures/flawed-evidence-block.md').read()}))" \
  | bash hooks/subagent-verification-gate.sh
```

Seven payload shapes are covered: clean block, flawed block, colon-heavy text,
raw non-JSON, content-block list, missing block, and empty payload.
