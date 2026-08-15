#!/usr/bin/env bash
# =============================================================================
# subagent-verification-gate.sh
# Hook: SubagentStop
#
# Replaces the predecessor suite's subagent-quality-gate.sh, which had a design
# flaw and several defects:
#
#   * It scored the agent's PROSE, not the code — grepping for the word "try"
#     to conclude error handling existed, and counting "{" as nesting depth.
#   * It collapsed everything into a weighted average, letting a critical
#     safety failure be offset by verbose, comment-rich output.
#   * `cut -d: -f2-` truncated agent output at the first colon.
#   * Issues from the 2nd and 3rd evaluators were concatenated without
#     newlines and silently dropped before reporting.
#   * `grep -c ... || echo 0` under `set -euo pipefail` could emit multi-line
#     output into an arithmetic comparison.
#   * Matched credential text was echoed into the report unredacted.
#
# This version extracts the agent's verification block and delegates judgment
# to verification_gate.py, which parses per item and applies the evidence
# rules. It emits no aggregate score.
#
# Contract: reads the hook payload as JSON on stdin, writes a decision object
# to stdout. Exits 0 always — the decision travels in the payload, so a hook
# problem never silently blocks legitimate work.
#
# SubagentStop payload fields this relies on:
#   last_assistant_message — the agent's final text. THIS is where the output
#                            lives; there is no `output`/`response` key. Reading
#                            the wrong field makes every delivery unparseable,
#                            which fails closed and blocks everything.
#   stop_hook_active       — true when a stop hook is already driving the
#                            session; blocking again from there loops.
#
# Decision object: a block is emitted as
#   {"hookSpecificOutput": {"hookEventName": "SubagentStop", "decision": "block"}}
# "block" is the only defined value. An approval emits NO decision key.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUITE_ROOT="$(dirname "$SCRIPT_DIR")"
GATE="${SUITE_ROOT}/scripts/verification_gate.py"

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
LOGS_DIR="${PROJECT_DIR}/.dev-suite/logs"
SESSION_ID="${CLAUDE_SESSION_ID:-$(date -u +%Y%m%d_%H%M%S)}"
LOG_FILE="${LOGS_DIR}/subagent_gate_${SESSION_ID}.log"

PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$LOGS_DIR" 2>/dev/null || true

log() {
    printf '[%s] [%s] %s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${*:2}" >> "$LOG_FILE" 2>/dev/null || true
}

emit() {
    # $1 decision (block|approve), $2 reason, $3 optional detail file
    local decision="$1" reason="$2" detail_file="${3:-}"
    "$PYTHON_BIN" - "$decision" "$reason" "$detail_file" <<'PYEOF'
import json, sys
decision, reason, detail_file = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {"reason": reason}
if decision == "block":
    # "block" is the only value SubagentStop defines. hookSpecificOutput is the
    # documented surface; the top-level key is retained for older CLI builds
    # that read the decision there.
    payload["hookSpecificOutput"] = {
        "hookEventName": "SubagentStop",
        "decision": "block",
        "reason": reason,
    }
    payload["decision"] = "block"
# Approval emits no decision at all — the absence of a block is what lets the
# subagent stop normally. There is no "approve" value in the contract, and
# sending one is indistinguishable from sending garbage.
if detail_file:
    try:
        with open(detail_file, encoding="utf-8", errors="replace") as handle:
            payload["report"] = handle.read()[:8000]
    except OSError:
        pass
# No aggregate score is emitted by design: one blocking item is a blocked
# delivery regardless of how many other items passed.
print(json.dumps(payload, indent=2))
PYEOF
}

# ---------------------------------------------------------------------------
# Read the full payload. Never truncate: the agent's output legitimately
# contains colons, pipes, and newlines.
# ---------------------------------------------------------------------------
PAYLOAD="$(cat 2>/dev/null || true)"

if [[ -z "${PAYLOAD//[[:space:]]/}" ]]; then
    log WARN "empty payload; approving without evaluation"
    emit approve "No subagent output to evaluate"
    exit 0
fi

if [[ ! -f "$GATE" ]]; then
    log ERROR "verification_gate.py not found at ${GATE}"
    emit approve "Verification gate unavailable — hook misconfigured, not blocking"
    exit 0
fi

BLOCK_FILE="$(mktemp)"
REPORT_FILE="$(mktemp)"
META_FILE="$(mktemp)"
trap 'rm -f "$BLOCK_FILE" "$REPORT_FILE" "$META_FILE"' EXIT

# ---------------------------------------------------------------------------
# Extract the agent's text from the payload using a real JSON parser, then
# isolate the verification block. Falls back to the raw payload when the
# input is not JSON, so the hook works under both invocation styles.
# ---------------------------------------------------------------------------
# The payload is passed by file, not by pipe: `python3 - <<EOF` already claims
# stdin for the program text, so a piped payload would be silently empty.
PAYLOAD_FILE="$(mktemp)"
printf '%s' "$PAYLOAD" > "$PAYLOAD_FILE"
trap 'rm -f "$BLOCK_FILE" "$REPORT_FILE" "$META_FILE" "$PAYLOAD_FILE"' EXIT

if ! "$PYTHON_BIN" - "$BLOCK_FILE" "$PAYLOAD_FILE" "$META_FILE" <<'PYEOF'
import json, re, sys

out_path, payload_path, meta_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(payload_path, encoding="utf-8", errors="replace") as handle:
    raw = handle.read()

text = raw
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    data = None

# `stop_hook_active` is true when a stop hook is already driving the session.
# Blocking again from here is how a stop hook turns into an infinite loop.
if isinstance(data, dict) and data.get("stop_hook_active") is True:
    with open(meta_path, "w", encoding="utf-8") as handle:
        handle.write("stop_hook_active\n")

if isinstance(data, dict):
    # SubagentStop carries the agent's final text in `last_assistant_message`.
    # The remaining keys are accepted so the hook still works when driven by
    # hand or by tests, but the real runtime field must be tried first.
    for key in (
        "last_assistant_message",
        "output",
        "response",
        "text",
        "content",
        "message",
        "result",
    ):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            text = value
            break
        if isinstance(value, list):
            parts = [
                block.get("text", "")
                for block in value
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ]
            if any(parts):
                text = "\n".join(parts)
                break

# Isolate the verification section if the agent labelled one; otherwise pass
# the whole text through and let the gate decide whether a block exists.
match = re.search(
    r"(?im)^#{1,6}\s*(?:pre-?output\s+verification|delivery\s+gate|verification)\b.*$",
    text,
)
if match:
    text = text[match.start():]

with open(out_path, "w", encoding="utf-8") as handle:
    handle.write(text)
PYEOF
then
    log ERROR "failed to extract agent text from payload"
    emit approve "Could not parse hook payload — not blocking"
    exit 0
fi

# ---------------------------------------------------------------------------
# Loop guard. If a stop hook is already active, this gate has already had its
# say once; blocking a second time is what produces a non-terminating loop.
# ---------------------------------------------------------------------------
if [[ -s "$META_FILE" ]]; then
    log INFO "stop_hook_active set; approving to break the stop loop"
    emit approve "A stop hook is already active — not blocking again"
    exit 0
fi

# ---------------------------------------------------------------------------
# Delegate the actual judgment.
#   0 = approved   1 = blocked   2 = approved with warnings   3 = unparseable
# ---------------------------------------------------------------------------
"$PYTHON_BIN" "$GATE" "$BLOCK_FILE" > "$REPORT_FILE" 2>&1
GATE_EXIT=$?

case "$GATE_EXIT" in
    0)
        log INFO "verification block approved"
        emit approve "Verification block approved — all items resolved" "$REPORT_FILE"
        ;;
    2)
        log INFO "verification block approved with warnings"
        emit approve "Approved with warnings — see report" "$REPORT_FILE"
        ;;
    1)
        log WARN "verification block blocked"
        emit block "Blocked by verification gate — see per-item report" "$REPORT_FILE"
        ;;
    3)
        # A missing or unparseable block on an agent that produced code is a
        # blocked delivery, not an approval: the gate has no evidence to act on.
        log WARN "verification block missing or unparseable"
        emit block \
            "No parseable pre-output verification block found. Agents producing code must emit one before delivery." \
            "$REPORT_FILE"
        ;;
    *)
        log ERROR "verification gate exited ${GATE_EXIT}"
        emit approve "Verification gate error — not blocking on tooling failure" "$REPORT_FILE"
        ;;
esac

exit 0
