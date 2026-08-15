# Changelog

All notable changes to the dev-automation-suite.

Format follows Keep a Changelog. Versioning is semantic.

## [3.2.0] — 2026-08-15

Readiness pass for terminal use. The package was structurally sound but did
not load: the manifests had been moved, the executable bits were never set in
git, and the hook read a payload shape Claude Code does not send.

### Fixed

- **Plugin manifest relocated back into the plugin.** `plugin.json` had been
  moved to the repository root, leaving `plugins/dev-automation-suite/` with
  no manifest and the root looking like a plugin with no components. It now
  sits at `plugins/dev-automation-suite/.claude-plugin/plugin.json`, where the
  spec puts it.
- **Marketplace `source` corrected.** The root manifest pointed at `./`, which
  resolves to the repository root — an install would have produced a plugin
  with no agents, commands, skill, or hook. It now points at
  `./plugins/dev-automation-suite`. Two tests pin the resolution.
- **Executable bits restored** on `bin/*` and `hooks/*.sh`. They were `100644`
  in git from the first commit, so a fresh clone could not run the hook
  (permission denied) or the PATH wrappers.
- **Hook reads `last_assistant_message`.** That is the field `SubagentStop`
  actually carries. Reading only the synthetic keys made every payload fall
  through to the raw JSON, where a verification block's headings are escaped
  text — so a clean, fully verified delivery was blocked in every real session.
- **`stop_hook_active` guard added.** A subagent that cannot emit a block was
  re-blocked up to Claude Code's limit of eight consecutive blocks. It now
  costs one round.

### Changed

- **`SubagentStop` matcher scoped** from `*` to
  `^(dev-automation-suite:)?code-(explorer|architect|reviewer)$`. The matcher
  runs against `agent_type`, so `*` applied this plugin's verification
  contract to `Explore`, `Plan`, and `general-purpose` — agents that never
  agreed to it and cannot satisfy it.
- **Model routing moved to the Claude 5 family**, by task shape rather than by
  phase number: validation, conductor, and complex work on `claude-opus-5`;
  discovery and report writing on `claude-sonnet-5` at `high`. Identifiers are
  pinned rather than aliased — an alias silently re-points on the next release,
  which changes a quality gate's behaviour without changing a line here.
- Token-budget pricing table extended to the Claude 5 models, with the
  estimate-until-measured caveat stated where the figures are used.

### Tests

81 → 89. The new cases pin the real `SubagentStop` payload shape, the
`stop_hook_active` guard, the matcher's scope in both directions (covers this
plugin's agents, excludes the built-ins), matcher/`agents/` drift, pinned
model identifiers, and marketplace `source` resolution.

## [3.0.0] — 2026-08-11

First release of the merged suite. Consolidates three previously separate
packages into one system with a single phase model, one script registry, and an
enforced output-verification gate.

### Provenance

Lineage established by checksum comparison across four sources before merging:

| Source | Disposition |
|---|---|
| `automate-dev` (installed, 21 files, Opus-4.7 routing) | **Head revision** — adopted as the enforcement core |
| `automate-dev.zip` (18 files, sonnet/opus routing) | Ancestor of the above; superseded |
| `.agents/automate-dev/` | Byte-identical to `automate-dev.zip`; superseded |
| `dev-automation-suite-main` (10 phase prompts, 22 plugins) | Lifecycle phases adopted; quality hook rejected and rewritten |
| `production-code-quality` (`.agents/skills/code-quality/`) | 5 scripts adopted |
| `agent-output-verification` | Templates and evidence model vendored |

The three `automate-dev` copies differed in one direction only — the installed
copy added content and removed none — establishing a clean ancestor/descendant
relationship. No copy with 8 agents was found in any source; the only 8-agent
directory in the ecosystem is `backend-development`, which also ships a
`feature-development` command, the likely source of the conflation.

### Added

- `scripts/suite_orchestrator.py` — unified 11-phase dispatch (0 Bootstrap
  through 10 Ship), replacing two separate phase models
- `scripts/script_registry.py` — declares invocation contracts, exit semantics
  and phase ownership for all 14 scripts in one place
- `scripts/verification_gate.py` — parses and enforces agent pre-output
  verification blocks; per-item, non-aggregated
- `scripts/stack_profile.py` — stack detection replacing hard-coded Flask/Mongo
  assumptions; composing profiles for Python/Flask, TypeScript/Expo/RN,
  Node/Express, frontend web, plus generic
- `scripts/_cli.py` — shared SIGPIPE handling
- `hooks/subagent-verification-gate.sh` — rewritten `SubagentStop` gate
- `hooks/hooks.json` — hook registration
- `tests/test_suite.py` — 36 regression tests, standard library only
- `references/output-verification.md`, `references/agent-roster.md`,
  `references/stack-profiles.md`, `references/hooks.md`
- Phases 0, 8, 9, 10 documented in `references/workflow-phases.md`
- Gate 7 and gate precedence rules in `references/quality-gates.md`
- `## Exit Criteria — Pre-Output Verification` on all three core agents

### Changed

- Phase model extended from 8 phases to 11, absorbing the lifecycle suite's
  security, observability and release phases
- `breaking_change_detector` and `verification_gate` now **halt** rather than
  fail: their failures require explicit resolution and are never auto-routed to
  the Fix phase
- Diff-based checks are skipped with a stated reason when no baseline exists,
  instead of being invoked with a missing argument and reported as ERROR

### Fixed

Defects in the predecessor `subagent-quality-gate.sh`, all now covered by
regression tests:

- **Design flaw** — the hook scored the agent's prose rather than the code,
  grepping for the word "try" to conclude error handling existed and counting
  `{` characters as nesting depth, then collapsing results into a weighted
  average that let a critical safety failure be offset by verbose output
- `cut -d: -f2-` truncated agent output at the first colon
- Issue collection concatenated evaluator outputs without newlines, silently
  dropping issues from the 2nd and 3rd evaluators
- `grep -ci … || echo 0` under `set -euo pipefail` could emit multi-line output
  into an arithmetic comparison
- Matched credential text was echoed into reports unredacted
- Stdin collision in the rewritten hook's extractor, found by its own test:
  `python3 - <<EOF` claims stdin for the program text, so a piped payload
  arrived empty. Payload is now passed by file.
- `BrokenPipeError` traceback when suite scripts were piped into `head`, which
  a calling hook read as a script crash

### Removed

Nothing. All 12 inherited scripts are carried over byte-identical, and no
inherited reference document was deleted.

### Vendored assets

| Asset | Source | Synced |
|---|---|---|
| `assets/verification-block-template.md` | `agent-output-verification` | 2026-08-11 |
| `assets/verification-block-evidence.md` | `agent-output-verification` | 2026-08-11 |
| Evidence model in `references/output-verification.md` | `agent-output-verification` | 2026-08-11 |

Amend upstream and re-vendor. A version bump in `agent-output-verification`
should surface here as a re-sync task rather than silent divergence.

## [2.0.0] — prior, untagged

The installed `automate-dev` head revision. Migrated agent routing to
`claude-opus-4-7` at `xhigh` effort, added `references/model-deployment.md`,
`references/token-budgeting.md` and `scripts/token_budget_monitor.py`. Never
carried a version field; recorded here retrospectively to close the ambiguity
that required a four-way checksum comparison to resolve.

## [1.x] — prior, untagged

Original `automate-dev`: 8-phase loop, 3 agents on `sonnet`/`sonnet`/`opus`,
6 scripts, no token budgeting.

## [3.0.1] — 2026-08-11

Claude Code plugin packaging. No change to gate logic or phase behaviour.

### Added

- `.claude-plugin/plugin.json` — plugin manifest
- `commands/run-phase.md`, `commands/verify-output.md`,
  `commands/detect-stack.md` — slash commands for the three main entry points
- `bin/dev-suite`, `bin/dev-suite-verify`, `bin/dev-suite-stack` — bare-command
  wrappers, added to the Bash tool's PATH while the plugin is enabled. They
  resolve the suite root from their own location rather than
  `CLAUDE_PLUGIN_ROOT`, so they also work from a plain checkout
- 10 further regression tests (`TestPluginManifest`) covering manifest shape,
  component placement, hook quoting, executable bits, and agent frontmatter

### Fixed

- **Hook command was unquoted.** `${CLAUDE_PLUGIN_ROOT}/hooks/...` breaks when
  the plugin cache path contains a space. The documented shell-form quoting
  (`"${CLAUDE_PLUGIN_ROOT}"/hooks/...`) is now used, with a regression test.
  Plugins are cached under `~/.claude/plugins/cache`, a path that can contain
  spaces on some systems, so this would have failed silently for those users.
- **`hooks/hooks.json` carried a `description` key** that is not part of the
  hooks schema. Removed; the explanation lives in `references/hooks.md`.

### Notes on the manifest

`commands`, `agents` and `hooks` are deliberately **not** declared. All three sit
at their default locations, so auto-discovery covers them, and declaring a
default path adds a failure mode without adding capability.

`skills` is likewise not declared: with `SKILL.md` at the plugin root and no
`skills/` directory, Claude Code loads it as a single-skill plugin and takes the
invocation name from the frontmatter `name` field. A `skills/` directory would
suppress that; a regression test guards against one being added.

## [3.1.0] — 2026-08-15

Adds a premise layer and a local project-lifecycle layer. No breaking changes:
all 46 prior tests pass unmodified, and every new gate behaviour is opt-in.

### Provenance

| Source | Disposition |
|---|---|
| `common-ground` command package (5 files) | Classification model adopted; storage and enforcement reimplemented locally |
| Project lifecycle documentation set (10 files) | Phase structure adopted; external service coupling removed |

**Assessment before integration.** The lifecycle set referenced eleven commands
(`intake:document-codebase`, `planning:epic-plan`, `execution:execute-ticket`
and others) that did not ship with it, and coupled to hosted Jira across 7 files
and Confluence across 7. Copying it verbatim would have planted eleven dangling
references and two external dependencies. It was adapted instead: the phase
structure is documented in `references/project-lifecycle.md`, work items are
local files, and no command is referenced that this package does not implement.

`common-ground` was self-contained and needed no such surgery. Its type/tier
model converges with the evidence model already in the suite — both separate how
a claim was derived from how confident anyone is in it — so it was integrated as
an enforcement layer rather than as documentation.

### Added

- `scripts/ground_file.py` — premise tracking by type (immutable audit trail)
  and tier (mutable confidence). High-impact premises default to `OPEN`.
  Registered as halting: an unvalidated premise cannot be repaired by the Fix
  phase, because the answer lives with the user
- `scripts/work_items.py` — local file-based epic and ticket tracking.
  Markdown is the source of truth, `index.json` is derived. Computes parallel
  execution waves; refuses out-of-order starts and reports dependency cycles
  rather than resolving them arbitrarily
- **Premise cross-check in `verification_gate.py`** (`--ground-file`). Each
  verification item is matched against OPEN premises by distinctive term
  overlap; two or more shared terms counts as a reference, one is coincidence.
  An item resting on an OPEN high-impact premise blocks even when the item is
  entirely correct about the code — faithfully implementing the wrong model is
  still wrong. This catches a failure class no other check in the suite can see
- `commands/common-ground.md`, `commands/work-items.md`
- `bin/dev-suite-ground`, `bin/dev-suite-work`
- `references/assumption-tracking.md`, `references/project-lifecycle.md`
- 26 further regression tests (72 total)

### Changed

- Phase 0 Bootstrap now surfaces premises alongside stack detection
- Phase 1 Analyse runs the premise check
- Core principle 5 added: no unvalidated premise

### Fixed

- **`work_items.py` reported the wrong cause for an incomplete ticket.** A
  ticket created with acceptance criteria but no description was warned about
  missing acceptance criteria, because a single boolean covered two distinct
  conditions. Each gap is now reported by name. Found by its own smoke test;
  a misleading diagnostic is worse than none, since it sends the fix to the
  wrong place.

### Not integrated, and why

- **Hosted tracker and documentation integrations.** Local files and CLI only.
- **Characterisation-test generation and system-description authoring** from the
  intake lineage. Both are worth doing and neither is a suite capability; the
  package does not claim to own them.
- **Multi-user work assignment, estimation, external status reporting.** These
  need a tracker with shared state, which would reintroduce the dependency this
  adaptation removed.

## [3.1.1] — 2026-08-15

Marketplace packaging. No behaviour change.

### Added

- `.claude-plugin/marketplace.json` — the suite hosts its own marketplace under
  the name `techcorp-plugins`, so it can be added and installed directly with
  `/plugin marketplace add` rather than requiring a separate catalog repository
- 9 marketplace regression tests (81 total), covering required fields, reserved
  and Desktop-rejected marketplace names, kebab-case, duplicate entries,
  name agreement between the entry and `plugin.json`, path traversal in
  relative sources, and rename-chain termination

### Changed

- `test_claude_plugin_dir_contains_only_the_manifest` renamed and tightened to
  `test_claude_plugin_dir_holds_only_manifest_files`. The original asserted the
  directory held exactly one file, which was a proxy for the real rule rather
  than the rule itself: `marketplace.json` legitimately belongs there, while a
  component directory never does. The assertion now names what is forbidden.
  The old test failed when `marketplace.json` was added, which is the test doing
  its job — the fix was to state the rule correctly, not to loosen it.

### Notes on version declaration

The marketplace entry deliberately omits `version`. Claude Code always takes the
`plugin.json` value without warning when both are set, so declaring it twice
lets a stale manifest silently mask the marketplace value. A regression test
asserts the version appears in exactly one place.
