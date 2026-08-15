# Project Lifecycle — the outer loop

<!-- ADAPTED from a five-phase lifecycle documentation set, synced 2026-08-15.
     The source coupled every phase to hosted Jira and Confluence and referenced
     eleven commands that did not ship with it. Both were removed: work items
     are local files (scripts/work_items.py), documents are local markdown, and
     no command is referenced here that this package does not implement. -->

The eleven phases in `references/workflow-phases.md` cover **one unit of work**
from analysis to ship. This outer loop covers **a project** — how work gets
identified, sequenced, and closed out.

The two nest. One pass through the outer Execution stage runs the full inner
eleven-phase loop for a single ticket.

```
 INTAKE ──▸ DISCOVERY* ──▸ PLANNING ──▸ EXECUTION ──▸ RETROSPECTIVE
   once      optional        per epic    per ticket      per epic
                                             │
                                             ▼
                                  ┌──────────────────────┐
                                  │ inner 11-phase loop  │
                                  │ bootstrap → ship     │
                                  └──────────────────────┘
```

## No external services

The lineage this was adapted from ran on hosted Jira and Confluence. This
implementation is local files and CLI only:

| Was | Is |
|---|---|
| Jira epics and tickets | `.dev-suite/work/` markdown files + derived `index.json` |
| Confluence documents | Local markdown under `docs/` |
| Ticket transitions via API | `work_items.py status <id> <status>` |
| Hosted parallel-wave planning | `work_items.py waves <epic>` |

Work items live in the repository beside the code they describe, travel with the
branch, and are reviewed in pull requests like anything else.

## Intake — once per project

Establishes baseline understanding of an existing codebase before feature work
begins.

```bash
python3 scripts/stack_profile.py .                    # what stack is this
python3 scripts/ground_file.py --project-root . check  # what are we assuming
python3 scripts/work_items.py --project-root . init    # work item store
```

Outputs: a detected stack profile, a recorded set of premises, and an initialised
work store. The premises matter most here — intake is when a project's
assumptions are most numerous and least examined.

Where the source lineage also produced characterisation tests and a system
description, those remain worth doing; they are project deliverables rather than
suite commands, so this package does not pretend to own them.

## Discovery — optional

Runs only when planning surfaces questions that cannot be answered from existing
knowledge. Not every piece of work needs it.

Record each unknown as an `uncertain` premise. That puts it at `OPEN`, which
blocks the gate on high-impact subjects until it is answered — so an unresolved
research question cannot quietly become an implementation detail.

```bash
python3 scripts/ground_file.py --project-root . add \
    "Offline support" "App must function without connectivity" --type uncertain
```

Humans do the actual research. Discovery is finished when every OPEN premise is
either promoted with evidence or explicitly deferred.

## Planning — per epic

Turns intent into an ordered, executable set of tickets.

```bash
python3 scripts/work_items.py --project-root . epic "Payment integration"
python3 scripts/work_items.py --project-root . ticket EPIC-1 "Schema migration" \
    --acceptance "table created" "rollback verified" \
    --body "Add the payments table with a reversible migration." \
    --files db/migrations/
python3 scripts/work_items.py --project-root . waves EPIC-1
```

A ticket is executable when it has acceptance criteria and a description.
`work_items.py` reports each missing piece by name, because a ticket with no
acceptance criteria has no definition of finished and any output can be argued
to satisfy it.

`waves` computes the dependency order and groups independent tickets so they can
run in parallel. A dependency cycle is reported as a cycle rather than resolved
arbitrarily — an arbitrary order through a cycle produces work done in the wrong
sequence with nothing indicating it.

## Execution — per ticket

Each ticket runs the inner loop:

```bash
python3 scripts/work_items.py --project-root . status T-1 in-progress
python3 scripts/suite_orchestrator.py run analyse . --targets <files>
# ... build, review, test, fix, simplify, validate ...
python3 scripts/work_items.py --project-root . status T-1 in-review
```

Starting a ticket whose dependencies are incomplete is refused. That is how a
dependency gets built on top of work that has not landed.

Implementation and completion are separate steps deliberately: long
implementations get compacted or interrupted, and completion tracking is the
first thing dropped when it is bundled into the same step.

## Retrospective — per epic

Closes the loop.

```bash
python3 scripts/work_items.py --project-root . list
python3 scripts/ground_file.py --project-root . check
python3 scripts/deployment_readiness.py .
```

Three things worth doing at the close:

1. **Revalidate premises.** An epic usually proves or disproves several. Promote
   what was confirmed, demote what was contradicted.
2. **Review the whole, not the diffs.** Incremental per-ticket updates miss
   architectural drift that is only visible across the epic.
3. **Record what was learned.** Per the suite's convention, a root-cause fix
   produces a named regression test; the same applies here — a lesson without an
   artifact is a lesson that will be relearned.

The updated premises feed the next cycle, which is the point: each iteration
starts better informed than the last.

## What this outer loop does not do

It does not assign work, estimate, or report status to anyone outside the
repository. Those need a tracker with multi-user state, and adding one would
reintroduce the external dependency this adaptation removed.
