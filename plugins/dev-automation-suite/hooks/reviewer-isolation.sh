#!/usr/bin/env bash
# =============================================================================
# reviewer-isolation.sh
# Hooks: PreToolUse (deny), SubagentStart (inject contract)
#
# The review packet controls what the reviewer is *handed*. This controls what
# it can *reach*. Both are needed: a reviewer given a clean packet that can then
# open .dev-suite/logs/ and read the author's session has been handed nothing
# and told everything.
#
# PreToolUse
#   Denies the reviewer any read into the work process — session logs, phase
#   state, ground-file narrative, agent transcripts. The reviewer keeps full
#   access to the codebase, because reviewing a diff means reading the code
#   around it; what it loses is the record of how the diff was produced.
#
# SubagentStart
#   Injects the blind-review contract into every reviewer spawn. The contract
#   then does not depend on the orchestrator remembering to include it — an
#   orchestrator deep in the problem is exactly the caller most likely to write
#   a helpful, leading prompt.
#
# Fails open on its own errors, and only on its own errors: a malformed payload
# or a missing interpreter must not wedge the session. A path that matches the
# denylist is denied even if everything else about the call looks fine.
# =============================================================================

set -uo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"

PAYLOAD="$(cat 2>/dev/null || true)"
if [[ -z "${PAYLOAD//[[:space:]]/}" ]]; then
    exit 0
fi

PAYLOAD_FILE="$(mktemp)"
printf '%s' "$PAYLOAD" > "$PAYLOAD_FILE"
trap 'rm -f "$PAYLOAD_FILE"' EXIT

"$PYTHON_BIN" - "$PAYLOAD_FILE" <<'PYEOF' || exit 0
import json
import re
import sys

CONTRACT = """You are reviewing independently. You have been given the original
task and the completed work, and deliberately nothing else: not the author's
reasoning, not the steps they took, not their own assessment of the result.

That omission is the point. Judge the work against the task on the evidence in
front of you, and reach your own conclusion about what it does.

If the material you were given includes the author's rationale, their
verification claims, a narrative of how the work was produced, or a restated
version of the task, stop and report the contamination instead of reviewing.
A review conducted on a framed packet reads as independent and is not, which is
worse than no review at all.

Do not go looking for the process: .dev-suite/ state, session logs, and agent
transcripts are out of bounds and reads against them are denied."""

#: Paths that hold the record of how the work was produced. The reviewer keeps
#: the rest of the repository — the artifact under review is not a secret.
#:
#: The last rule is scoped to `.claude/`, not to the extension. It was
#: `\.jsonl$`, which denied every .jsonl anywhere: transcripts are jsonl, but so
#: is an ordinary project audit trail, and a host that keeps its gate records in
#: .jsonl had them blanket-denied to the reviewer. The concern is transcripts,
#: and transcripts live under `.claude/` — the two rules above already cover the
#: known locations, and this covers the rest of that tree without reaching
#: outside it.
DENIED = re.compile(
    r'(^|/)\.dev-suite(/|$)'
    r'|(^|/)\.claude/projects(/|$)'
    r'|/subagents/'
    r'|(^|/)\.claude/.*\.jsonl$',
)

#: Bash is denied only when the command line reaches into those same paths;
#: the reviewer still needs a shell for `git diff`, `grep`, and test runs.
DENIED_IN_COMMAND = re.compile(r'\.dev-suite|\.claude/projects|subagents/')

#: Which inputs of each tool name a *location*. This has to be per tool,
#: because the same key means different things: Glob's `pattern` is a path
#: pattern, while Grep's `pattern` is the regex being searched for. Treating
#: them alike is wrong in both directions — it lets `Grep(glob=".dev-suite/**")`
#: through, and it blocks a reviewer legitimately grepping the source for the
#: string ".dev-suite".
LOCATION_INPUTS = {
    'Read': ('file_path',),
    'NotebookRead': ('notebook_path',),
    'Glob': ('pattern', 'path'),
    'Grep': ('path', 'glob'),
}

#: Anything not named above is checked against every key that has ever meant a
#: location. A tool added later should fail closed rather than pass silently.
FALLBACK_INPUTS = ('file_path', 'notebook_path', 'path', 'glob', 'pattern')

REVIEWER = re.compile(r'^(dev-automation-suite:)?code-reviewer$')


def emit(obj):
    print(json.dumps(obj, indent=2))


try:
    with open(sys.argv[1], encoding='utf-8', errors='replace') as handle:
        payload = json.load(handle)
except (OSError, ValueError):
    sys.exit(0)

if not isinstance(payload, dict):
    sys.exit(0)

if not REVIEWER.match(str(payload.get('agent_type') or '')):
    sys.exit(0)

event = payload.get('hook_event_name')

if event == 'SubagentStart':
    emit({'hookSpecificOutput': {
        'hookEventName': 'SubagentStart',
        'additionalContext': CONTRACT,
    }})
    sys.exit(0)

if event != 'PreToolUse':
    sys.exit(0)

tool_input = payload.get('tool_input') or {}
if not isinstance(tool_input, dict):
    sys.exit(0)

tool_name = str(payload.get('tool_name') or '')

candidates = []
for key in LOCATION_INPUTS.get(tool_name, FALLBACK_INPUTS):
    value = tool_input.get(key)
    if isinstance(value, str):
        candidates.append((key, value, DENIED))
command = tool_input.get('command')
if isinstance(command, str):
    candidates.append(('command', command, DENIED_IN_COMMAND))

for key, value, pattern in candidates:
    # Normalise separators: a backslash path never matches a forward-slash
    # rule, and the tool call would proceed as though the hook had not run.
    if pattern.search(value.replace('\\', '/')):
        emit({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': (
                f'Independent review: {key} reaches into the work process '
                f'({value}). You have the original task and the completed work; '
                'how the work was produced is deliberately withheld. Review the '
                'artifact, or report that you cannot.'
            ),
        }})
        sys.exit(0)

sys.exit(0)
PYEOF

exit 0
