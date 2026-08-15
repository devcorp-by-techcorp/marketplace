# Independent Review

## The problem

An agent that has just built something is the worst available judge of it, and
an agent that has *read the builder's account* is the second worst.

The second one is the trap, because it looks solved. Delegating review to a
separate agent feels like independence — different context window, different
instance, a clean start. But the reviewer's prompt is written by an
orchestrator that has been inside the problem for twenty turns, and that
orchestrator does not leak the reasoning by being careless. It leaks by being
helpful:

> Review the retry logic I added around the timeout — I used exponential
> backoff because the fixed delay was hammering the upstream. Tests pass.

Every clause there is true, useful, and disqualifying. The reviewer now knows
what the change is *for*, why the alternative was rejected, and that it works.
It will check whether exponential backoff was implemented correctly. It will
not ask whether retrying was the right response to that failure at all — the
question the framing quietly closed.

This is not a diligence problem, and telling the reviewer to "be objective"
does not touch it. The information is already in the context window.

## The rule

A reviewing agent receives exactly two things:

| | |
|---|---|
| **The original task** | Verbatim, as the requester wrote it, pinned by hash before work began |
| **The completed work** | The diff, and nothing about how it came to exist |

Withheld: the author's reasoning, the intermediate steps, the tool calls, the
problems hit and recovered from, the author's own verification block, and the
author's assessment of the result.

The reviewer reads the task, reads the artifact, and forms its own account of
what the work does. Where the two disagree, the task wins.

## Why the task is pinned by hash

This is the least obvious rule and the one that does the most work.

An orchestrator asked to restate the task does not restate it neutrally. It
compresses twenty turns of understanding into a sentence, and that sentence
carries the conclusion:

| The requester wrote | The orchestrator would write |
|---|---|
| "Uploads are timing out for some users." | "Review the retry logic added to fix the upload timeout race." |

The second version has already decided that there was a race, that retrying
addresses it, and that the diff is a fix. A reviewer handed that will confirm
the retry logic. It will not consider that the timeout was a symptom of an
unbounded upload size, because it was never told there was a question.

So `review_packet.py record` pins the task before work starts, and `build`
quotes it rather than accepting one. `check` compares hashes, so a packet that
arrives from anywhere else is still caught.

Recording is refused after a differing task is already on file. A task
re-recorded mid-work is the author's summary of what they built.

## The four layers

No single mechanism is sufficient, and each covers a gap the others leave.

### 1. Structural — the workflow

`workflows/independent-review.js` holds the orchestration in a script, so
intermediate results live in script variables instead of a context window. The
reviewer prompts are constructed from `task` and `diff`; there is no third
variable holding the builder's account for them to be built from. This removes
the opportunity rather than asking an orchestrator to resist it.

```
/dev-automation-suite:independent-review
```

Reviewers run in parallel and do not see each other's findings — three
reviewers shown a first opinion converge on it, which buys the appearance of
agreement rather than three looks at the code.

### 2. Mechanical — the packet

`scripts/review_packet.py` builds a packet from the pinned task and a diff, and
checks any packet for contamination. `check` is separate from `build` because a
packet assembled by hand still has to be checkable; enforcement that only works
when you used the right tool is not enforcement.

```bash
python3 scripts/review_packet.py record  <root> --task-file request.txt
python3 scripts/review_packet.py build   <root> --diff work.diff -o packet.md
python3 scripts/review_packet.py check   packet.md --project-root <root>
```

Rules, each named so the report can say which line to remove:

| Rule | Catches |
|---|---|
| `extra_section` | Any heading beyond `## Task` and `## Work` |
| `missing_section` | A packet with nothing to review, or nothing to review against |
| `task_tampering` | A task that was restated rather than quoted |
| `author_narrative` | "I chose", "my approach", "first I… then I…" |
| `verification_block` | The author's own evidence table or status vocabulary |
| `self_assessment` | "All tests pass", "ready for merge", "I verified" |
| `process_reference` | `.dev-suite/`, transcripts, "my earlier attempt" |

Prose rules are matched only outside fenced blocks. A diff legitimately
contains `I` in a string literal and `PASS` in a test name; scanning the
artifact for words *about* the artifact is how a checker like this starts
rejecting correct packets and gets switched off.

### 3. Tool-boundary — the isolation hook

`hooks/reviewer-isolation.sh` on `PreToolUse` denies the reviewer any read into
`.dev-suite/`, session logs, agent transcripts, and `.jsonl` files — by path
and by shell command. A reviewer handed a clean packet that can then open the
author's session log has been handed nothing and told everything.

The reviewer keeps full access to the codebase. Reviewing a diff means reading
the code around it; what it loses is the record of how the diff was produced.
Bash stays available for `git diff`, `grep`, and test runs — only commands
reaching into the process paths are denied.

### 4. Contractual — injected at spawn

The same hook on `SubagentStart` injects the blind-review contract into every
reviewer spawn. The contract then does not depend on the orchestrator
remembering to include it, and the orchestrator deep in the problem is exactly
the caller least likely to.

## The reviewer's own verification block

The `SubagentStop` gate still applies to the reviewer, and its block covers
**its review**, not the author's work: whether it read every changed hunk,
whether it ran what it claims to have run, whether a finding was observed in
the diff or inferred from naming.

"The author says the tests pass" is not evidence the reviewer has. It either
ran them or it did not.

These two mechanisms do not overlap. The gate reads what the reviewer produced;
the packet governs what the reviewer was given.

## What a contaminated packet means

`review_packet` **halts** rather than failing. Halting checks are not routed to
the Fix phase, because there is nothing to fix in the code — the review was
never conducted under the conditions it claims.

If a reviewer reports contamination, discard every review in that run. A framed
reviewer does not become independent because two others agreed with it. Rebuild
the packet and re-run.

Do not summarise the removed content for the reviewer instead. A summary of the
process is still the process.

## When this does not apply

Phases 2 and 5 — Build and Fix — are agent-led but not *reviewing*: the agent
is producing work, not judging someone else's. They require a verification
block and no packet.

Phase 6, Simplify, is script-driven. Phases 8–10 apply their own passes to the
whole artifact rather than reviewing a specific delivery.

Blind review is for the two phases where one agent judges another's output:
**3 (Review)** and **7 (Validate)**.
