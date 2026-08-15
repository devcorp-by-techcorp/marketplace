export const meta = {
  name: 'independent-review',
  description:
    'Review completed work against the original task using reviewers that never ' +
    'see how the work was produced. Builder output stays in script variables; ' +
    'each reviewer is handed only the task and the diff.',
}

// Why this is a workflow and not a delegating agent.
//
// When an orchestrating agent spawns a reviewer, it composes the reviewer's
// prompt out of its own context — and its context is saturated with how the
// work was produced. It does not have to leak the reasoning deliberately; it
// leaks by being helpful. "Check the retry logic I added around the timeout"
// is a reasonable sentence and an already-framed review.
//
// A workflow removes the opportunity rather than asking anyone to resist it.
// Intermediate results live in script variables instead of a context window,
// so the reviewers below are constructed from `task` and `diff` and there is
// no third variable holding the author's account for them to be built from.
//
// Usage:  /dev-automation-suite:independent-review
//         args: { task, diff, modes?, root? }
//         `task` must be the request as the requester wrote it. If you find
//         yourself improving it, that is the failure this workflow prevents.

const input = args ?? {}

const task = (input.task ?? '').trim()
const diff = (input.diff ?? '').trim()
const root = input.root ?? '.'
const modes = input.modes ?? [
  'simplicity, DRY, and elegance',
  'bugs and functional correctness',
  'project conventions and abstractions',
]

if (!task || !diff) {
  return {
    error:
      'independent-review needs both `task` (the original request, verbatim) ' +
      'and `diff` (the completed work). One without the other is not reviewable.',
  }
}

// The packet is assembled once and reused verbatim for every reviewer, so no
// reviewer can receive a slightly different framing from another.
const packet = [
  '## Task', '', task, '',
  '## Work', '', '```diff', diff, '```',
].join('\n')

// Reviewers run in parallel and independently. They do not see each other's
// findings: three reviewers shown a first opinion converge on it, which buys
// the appearance of agreement rather than three looks at the code.
const reviews = await pipeline(modes, mode =>
  agent(
    [
      `Review the completed work below against the original task.`,
      `Focus this pass on ${mode}.`,
      ``,
      `You have the task and the finished artifact. You do not have the`,
      `author's reasoning, their process, or their assessment — that omission`,
      `is deliberate. Form your own account of what the diff does.`,
      ``,
      `If what follows contains the author's rationale, their verification`,
      `claims, or a task that reads like a summary of the work rather than a`,
      `request for it, report that instead of reviewing.`,
      ``,
      packet,
    ].join('\n'),
    {
      subagent_type: 'dev-automation-suite:code-reviewer',
      label: mode,
      schema: {
        type: 'object',
        required: ['verdict', 'findings'],
        properties: {
          verdict: { type: 'string', enum: ['pass', 'changes_required', 'contaminated'] },
          findings: {
            type: 'array',
            items: {
              type: 'object',
              required: ['severity', 'location', 'problem'],
              properties: {
                severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
                location: { type: 'string' },
                problem: { type: 'string' },
                evidence: { type: 'string' },
              },
            },
          },
        },
      },
    },
  ),
)

// `pipeline` yields null for an agent that was stopped or hit an unrecoverable
// error. A dropped reviewer is a thinner review, not a passed one — it is
// reported rather than filtered away, because a gate that silently loses a
// check is the failure mode this suite exists to prevent.
const completed = reviews.filter(Boolean)
const dropped = modes.filter((_, i) => !reviews[i])

const contaminated = completed.filter(r => r.verdict === 'contaminated')
if (contaminated.length) {
  return {
    verdict: 'HALT',
    reason:
      'A reviewer reported that the material it was given exposed the work ' +
      'process. Every review in this run is suspect — a framed reviewer does ' +
      'not become independent because the other two agreed with it.',
    reports: contaminated,
  }
}

// The consolidating agent sees the findings and the same task, never the diff's
// authorship or the process. Its job is ranking and de-duplication, not a
// fourth opinion — and it is told so, because a consolidator that re-reviews
// quietly overrides three independent passes with one dependent one.
const findings = completed.flatMap(r => r.findings ?? [])

if (!findings.length) {
  return {
    verdict: completed.length ? 'pass' : 'inconclusive',
    reviewsCompleted: completed.length,
    reviewsDropped: dropped,
    findings: [],
  }
}

const consolidated = await agent(
  [
    `Merge these independent review findings into one ranked list.`,
    `De-duplicate findings that describe the same defect in different words.`,
    `Rank by severity, then by how load-bearing the affected code is.`,
    ``,
    `Do not add findings of your own and do not soften or drop a finding`,
    `because the others did not raise it — one reviewer noticing something the`,
    `other two missed is the reason there are three.`,
    ``,
    `Original task:`,
    task,
    ``,
    `Findings:`,
    JSON.stringify(findings, null, 2),
  ].join('\n'),
  { label: 'consolidate' },
)

return {
  verdict: findings.some(f => ['critical', 'high'].includes(f.severity))
    ? 'changes_required'
    : 'pass_with_findings',
  reviewsCompleted: completed.length,
  reviewsDropped: dropped,
  root,
  consolidated,
  findings,
}
