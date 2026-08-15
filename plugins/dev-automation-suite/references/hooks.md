# Hook Wiring

## SubagentStop — the verification gate

`hooks/subagent-verification-gate.sh` is the enforcement point. Registered for
all subagents via `hooks/hooks.json`.

**Flow**: agent finishes → hook reads payload → extracts the verification block
→ delegates to `scripts/verification_gate.py` → emits an approve/block decision.

**Payload handling.** SubagentStop delivers the agent's final text in
**`last_assistant_message`**. That is the field to read; there is no `output` or
`response` key on this event. The hook also accepts `output`, `response`,
`text`, `content`, `message`, `result` (including content-block list form) and
raw text, but only so hand-driven invocation and fixtures keep working — the
runtime field is tried first. The full payload is read; nothing is truncated.
Agent output legitimately contains colons, pipes, and newlines.

Fields consumed:

| Field | Use |
|---|---|
| `last_assistant_message` | the agent's final text — the thing being judged |
| `stop_hook_active` | true when a stop hook is already driving the session; the gate approves immediately rather than blocking into a loop |

**Decision object.** A block goes in the `hookSpecificOutput` envelope, which is
where SubagentStop reads it. The top-level `decision` is retained alongside it
for older CLI builds:

```json
{ "hookSpecificOutput": { "hookEventName": "SubagentStop", "decision": "block",
    "reason": "Blocked by verification gate — see per-item report" },
  "decision": "block",
  "reason": "Blocked by verification gate — see per-item report",
  "report": "…full per-item output…" }
```

`"block"` is the **only** value the field defines. An approval emits no
decision key at all — absence of a block is what lets the subagent stop. Never
emit `"decision": "approve"`; it is not in the contract and behaves the same as
sending nonsense.

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

# Manual single case, in the shape the runtime actually sends
python3 -c "import json;print(json.dumps({'hook_event_name':'SubagentStop','stop_hook_active':False,'last_assistant_message':open('tests/fixtures/flawed-evidence-block.md').read()}))" \
  | bash hooks/subagent-verification-gate.sh
```

New hook tests must build their payload with
`TestHook._subagent_stop_payload()` rather than hand-rolling a dict. The suite
previously tested seven payload shapes, none of which was the one SubagentStop
sends — so the gate blocked every delivery in production while all tests passed.
The builder exists to make that failure mode unrepeatable.

Covered: the real SubagentStop payload (clean, flawed, and missing block), the
`hookSpecificOutput` envelope shape, approval emitting no decision, the
`stop_hook_active` loop guard, plus colon-heavy text, raw non-JSON, legacy
`output` key, content-block list, and empty payload.
