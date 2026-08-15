#!/usr/bin/env python3
"""
Suite Orchestrator — single entry point for the unified phase model.

Two workflow lineages are merged here. The build-review-test-fix loop comes from
automate-dev; the lifecycle phases beyond shipping code (harden, observe,
release) come from the phase-prompt suite. Scripts from both lineages, plus the
suite-native verification gate, are dispatched through ``script_registry`` so no
call shape is hard-coded in this file.

Phase model:

    0  Bootstrap   budget init, stack profile detection
    1  Analyse     inventory, dependency map, acceptance criteria, plan
    2  Build       implementation (agent-led; gate applies to agent output)
    3  Review      script checks + agent review + verification gate
    4  Test        test execution
    5  Fix         root-cause fixes, band-aid rejection
    6  Simplify    complexity reduction, behaviour preserved
    7  Validate    full gate before hardening
    8  Harden      security review pass
    9  Observe     observability and performance pass
    10 Ship        deployment readiness, docs, release

Design rules this file enforces:

  * No aggregate score. Phases report per-check verdicts. A single HALT is a
    stopped workflow regardless of how many checks passed.
  * Diff-based checks are skipped explicitly, with a stated reason, when no
    baseline file exists — never invoked with a missing argument and reported
    as a spurious ERROR.
  * State writes are opt-in. ``--dry-run`` is the default for anything that
    touches disk; ``--commit`` is required to persist.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import script_registry as registry  # noqa: E402
from script_registry import (  # noqa: E402
    BLOCKING_VERDICTS, ERROR, FAIL, HALT, NEEDS_APPROVAL, PASS, WARN,
    RegistryError, ScriptSpec,
)

STATE_DIR_NAME = '.dev-suite'
SCRIPT_TIMEOUT_SECONDS = 300

SKIPPED = 'SKIPPED'


@dataclass
class PhaseSpec:
    number: int
    name: str
    purpose: str
    #: registry names run automatically; agent-led phases may have none
    scripts: tuple[str, ...] = ()
    agent_led: bool = False
    requires_verification_block: bool = False


PHASES: dict[int, PhaseSpec] = {
    0: PhaseSpec(0, 'bootstrap',
                 'Stack detection, premise surfacing, budget initialisation',
                 scripts=('stack_profile', 'ground_file')),
    1: PhaseSpec(1, 'analyse', 'Inventory, dependency map, acceptance criteria',
                 scripts=('orchestrator', 'ground_file')),
    2: PhaseSpec(2, 'build', 'Implementation', agent_led=True,
                 requires_verification_block=True),
    3: PhaseSpec(3, 'review', 'Automated review, compatibility and preservation checks',
                 scripts=('code_review', 'breaking_changes', 'compatibility',
                          'preservation'),
                 agent_led=True, requires_verification_block=True),
    4: PhaseSpec(4, 'test', 'Test execution', scripts=('orchestrator',)),
    5: PhaseSpec(5, 'fix', 'Root-cause fixes with band-aid rejection',
                 scripts=('fix_validator',), agent_led=True,
                 requires_verification_block=True),
    6: PhaseSpec(6, 'simplify', 'Complexity reduction with behaviour preserved',
                 scripts=('simplifier',)),
    7: PhaseSpec(7, 'validate', 'Full quality gate',
                 scripts=('code_review', 'breaking_changes', 'compatibility',
                          'preservation', 'self_assessment'),
                 agent_led=True, requires_verification_block=True),
    8: PhaseSpec(8, 'harden', 'Security hardening pass',
                 scripts=('deployment_readiness',), agent_led=True),
    9: PhaseSpec(9, 'observe', 'Observability and performance pass', agent_led=True),
    10: PhaseSpec(10, 'ship', 'Deployment readiness and release',
                  scripts=('deployment_readiness',)),
}

PHASE_BY_NAME = {spec.name: spec for spec in PHASES.values()}


@dataclass
class CheckResult:
    script: str
    verdict: str
    exit_code: Optional[int] = None
    command: str = ''
    detail: str = ''
    skipped_reason: str = ''


@dataclass
class PhaseResult:
    phase: int
    name: str
    timestamp: str
    checks: list[CheckResult] = field(default_factory=list)
    halted: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> list[CheckResult]:
        return [c for c in self.checks if c.verdict in BLOCKING_VERDICTS]

    @property
    def verdict(self) -> str:
        """Worst verdict present. Deliberately not an average."""
        if any(c.verdict == HALT for c in self.checks):
            return HALT
        if any(c.verdict == ERROR for c in self.checks):
            return ERROR
        if any(c.verdict == FAIL for c in self.checks):
            return FAIL
        if any(c.verdict == NEEDS_APPROVAL for c in self.checks):
            return NEEDS_APPROVAL
        if any(c.verdict == WARN for c in self.checks):
            return WARN
        return PASS


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def run_script(
    spec: ScriptSpec,
    timeout: int = SCRIPT_TIMEOUT_SECONDS,
    **kwargs,
) -> CheckResult:
    """Invoke one registered script and normalise its outcome."""
    try:
        argv = spec.build_argv(**kwargs)
        command = spec.command_string(**kwargs)
    except RegistryError as exc:
        return CheckResult(
            script=spec.name, verdict=SKIPPED,
            skipped_reason=f'contract not satisfiable: {exc}',
        )

    try:
        completed = subprocess.run(
            [sys.executable, *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            script=spec.name, verdict=ERROR, command=command,
            detail=f'timed out after {timeout}s',
        )
    except OSError as exc:
        return CheckResult(
            script=spec.name, verdict=ERROR, command=command,
            detail=f'could not execute: {exc}',
        )

    verdict = spec.interpret_exit(completed.returncode)
    detail = (completed.stderr or completed.stdout or '').strip()
    return CheckResult(
        script=spec.name,
        verdict=verdict,
        exit_code=completed.returncode,
        command=command,
        detail=detail[:800],
    )


def run_phase(
    phase: int,
    project_root: str,
    targets: Optional[list[str]] = None,
    original: Optional[str] = None,
    verification_block: Optional[str] = None,
    stack: str = '',
) -> PhaseResult:
    """Run every script a phase owns, plus its verification gate if applicable."""
    spec = PHASES[phase]
    result = PhaseResult(phase=phase, name=spec.name, timestamp=_now())
    targets = targets or []
    primary = targets[0] if targets else None

    for script_name in spec.scripts:
        script = registry.get(script_name)

        if script.requires_original and not original:
            result.checks.append(CheckResult(
                script=script.name, verdict=SKIPPED,
                skipped_reason=(
                    'no baseline file supplied; diff-based check does not apply '
                    'to newly created files'
                ),
            ))
            continue

        kwargs: dict = {
            'project_root': project_root,
            'target': primary,
            'targets': targets,
            'original': original,
        }
        if script.name == 'orchestrator':
            kwargs['subcommand'] = {1: 'analyse', 4: 'test', 7: 'validate'}.get(phase)
        if script.name == 'stack_profile':
            kwargs = {'project_root': project_root}
        if script.name == 'deployment_readiness':
            kwargs = {'project_root': project_root}
        if script.name == 'ground_file':
            kwargs = {'project_root': project_root, 'subcommand': 'check'}
        if script.name == 'work_items':
            kwargs = {'project_root': project_root, 'subcommand': 'list'}

        result.checks.append(run_script(script, **kwargs))

    if spec.requires_verification_block:
        if verification_block:
            gate = registry.get('verification_gate')
            gate_kwargs = {'target': verification_block, 'stack': stack}
            result.checks.append(run_script(gate, **gate_kwargs))
        else:
            result.checks.append(CheckResult(
                script='verification_gate', verdict=HALT,
                skipped_reason=(
                    f'phase {phase} ({spec.name}) is agent-led and requires a '
                    'pre-output verification block; none was supplied. An '
                    'unverified agent delivery does not pass this phase.'
                ),
                detail='supply --verification-block <file>',
            ))

    if any(c.verdict == HALT for c in result.checks):
        result.halted = True
        result.notes.append(
            'workflow halted — halting checks are not routed to the Fix phase; '
            'they require explicit resolution'
        )

    return result


def render_phase(result: PhaseResult) -> str:
    spec = PHASES[result.phase]
    lines = [
        f'Phase {result.phase} — {result.name}',
        '=' * 68,
        spec.purpose,
        f'Verdict: {result.verdict}' + ('   [HALTED]' if result.halted else ''),
        '',
    ]
    for check in result.checks:
        lines.append(f'  [{check.verdict:>14}] {check.script}')
        if check.skipped_reason:
            lines.append(f'                   {check.skipped_reason}')
        if check.command:
            lines.append(f'                   $ {check.command}')
        if check.detail and check.verdict in BLOCKING_VERDICTS:
            first = check.detail.splitlines()[0] if check.detail.splitlines() else ''
            lines.append(f'                   {first[:110]}')
    lines.append('')
    for note in result.notes:
        lines.append(f'note: {note}')
    lines.append('')
    lines.append('This phase reports per-check verdicts. No aggregate score is')
    lines.append('produced: one halting check is a stopped workflow regardless of')
    lines.append('how many other checks passed.')
    return '\n'.join(lines)


def save_state(result: PhaseResult, project_root: str, commit: bool) -> Optional[Path]:
    """Persist the phase result. No-op unless ``commit`` is set."""
    if not commit:
        return None
    state_dir = Path(project_root) / STATE_DIR_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f'phase-{result.phase:02d}-{result.name}.json'
    path.write_text(json.dumps(asdict(result), indent=2), encoding='utf-8')
    return path


def cmd_run(args: argparse.Namespace) -> int:
    if args.phase in PHASE_BY_NAME:
        phase_number = PHASE_BY_NAME[args.phase].number
    else:
        try:
            phase_number = int(args.phase)
        except ValueError:
            print(f'error: unknown phase {args.phase!r}', file=sys.stderr)
            return 3
    if phase_number not in PHASES:
        print(f'error: phase {phase_number} is not defined', file=sys.stderr)
        return 3

    absent = registry.missing_scripts()
    if absent:
        print('error: registered scripts missing from disk:', file=sys.stderr)
        for name in absent:
            print(f'  - {name}', file=sys.stderr)
        return 3

    result = run_phase(
        phase_number,
        project_root=args.project_root,
        targets=args.targets,
        original=args.original,
        verification_block=args.verification_block,
        stack=args.stack,
    )

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(render_phase(result))

    written = save_state(result, args.project_root, args.commit)
    if written:
        print(f'\nstate written: {written}')
    elif not args.json:
        print('\n(dry run — pass --commit to persist phase state)')

    if result.halted:
        return 2
    if result.verdict in BLOCKING_VERDICTS:
        return 1
    return 0


def cmd_phases(_args: argparse.Namespace) -> int:
    print('Unified Phase Model')
    print('=' * 68)
    for spec in PHASES.values():
        scripts = ', '.join(spec.scripts) or '—'
        flags = []
        if spec.agent_led:
            flags.append('agent-led')
        if spec.requires_verification_block:
            flags.append('gate required')
        flag_text = f'  [{", ".join(flags)}]' if flags else ''
        print(f'{spec.number:>2}  {spec.name:<11}{spec.purpose}{flag_text}')
        print(f'    scripts: {scripts}')
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Unified orchestrator for the dev-automation-suite phase model.',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    run_parser = sub.add_parser('run', help='Run a workflow phase')
    run_parser.add_argument('phase', help='Phase number (0-10) or name')
    run_parser.add_argument('project_root', help='Project root directory')
    run_parser.add_argument('--targets', nargs='+', default=[], help='Target files')
    run_parser.add_argument('--original', help='Baseline file for diff-based checks')
    run_parser.add_argument(
        '--verification-block',
        help='File containing the agent pre-output verification block',
    )
    run_parser.add_argument('--stack', default='', help='Stack profile name')
    run_parser.add_argument('--json', action='store_true', help='Emit JSON')
    run_parser.add_argument(
        '--commit',
        action='store_true',
        help='Persist phase state to .dev-suite/ (default is dry run)',
    )
    run_parser.set_defaults(func=cmd_run)

    phases_parser = sub.add_parser('phases', help='Show the phase model')
    phases_parser.set_defaults(func=cmd_phases)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    from _cli import guard_broken_pipe
    guard_broken_pipe(main)
