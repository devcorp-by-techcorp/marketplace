#!/usr/bin/env python3
"""
Script Registry — single source of truth for how every suite script is invoked.

The suite carries scripts from two lineages with incompatible CLI conventions:

  * automate-dev lineage   — flag-based   (``<file> --project-root <root>``)
  * production-code-quality lineage — positional (``<original> <modified>``)

Wiring those call shapes into the orchestrator by hand is how drift starts. This
module declares each script's contract once, exposes a builder that produces the
correct argv, and maps scripts to the phases that own them. Every caller in the
suite goes through here.

Exit-code semantics also differ per lineage and are declared rather than assumed:
some scripts use exit 1 for FAIL, ``self_assessment`` adds exit 2 for
"requires approval". ``interpret_exit`` normalises these to suite verdicts.

Standard library only. No side effects on import.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

SCRIPT_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Verdict vocabulary
# --------------------------------------------------------------------------

PASS = 'PASS'
WARN = 'WARN'
FAIL = 'FAIL'
HALT = 'HALT'            # blocking; requires user intervention
NEEDS_APPROVAL = 'NEEDS_APPROVAL'
ERROR = 'ERROR'          # the script itself failed to run

BLOCKING_VERDICTS = frozenset({FAIL, HALT, ERROR})


class RegistryError(ValueError):
    """Raised when a script is requested that is not registered, or required
    arguments for its contract are missing."""


# --------------------------------------------------------------------------
# Argv builders — one per call shape
# --------------------------------------------------------------------------

def _build_target_with_root(
    script: Path,
    target: Optional[str] = None,
    project_root: Optional[str] = None,
    original: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <target> --project-root <root> [--original <original>]``"""
    if not target:
        raise RegistryError('target is required')
    if not project_root:
        raise RegistryError('project_root is required')
    argv = [str(script), target, '--project-root', project_root]
    if original:
        argv += ['--original', original]
    return argv


def _build_two_positional(
    script: Path,
    original: Optional[str] = None,
    target: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <original> <modified>`` — production-code-quality lineage."""
    if not original:
        raise RegistryError('original is required')
    if not target:
        raise RegistryError('target is required')
    return [str(script), original, target]


def _build_target_then_root_positional(
    script: Path,
    target: Optional[str] = None,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <target_file> <project_root>`` — compatibility_checker."""
    if not target:
        raise RegistryError('target is required')
    if not project_root:
        raise RegistryError('project_root is required')
    return [str(script), target, project_root]


def _build_fix_validator(
    script: Path,
    original: Optional[str] = None,
    target: Optional[str] = None,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <original> <fixed> --project-root <root>``"""
    if not original:
        raise RegistryError('original is required')
    if not target:
        raise RegistryError('target is required')
    if not project_root:
        raise RegistryError('project_root is required')
    return [str(script), original, target, '--project-root', project_root]


def _build_self_assessment(
    script: Path,
    target: Optional[str] = None,
    original: Optional[str] = None,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <target> [--compare <original>] [--project-root <root>]``"""
    if not target:
        raise RegistryError('target is required')
    argv = [str(script), target]
    if original:
        argv += ['--compare', original]
    if project_root:
        argv += ['--project-root', project_root]
    return argv


def _build_rn_analyzer(
    script: Path,
    target: Optional[str] = None,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <target> [--project-root <root>]``"""
    if not target:
        raise RegistryError('target is required')
    argv = [str(script), target]
    if project_root:
        argv += ['--project-root', project_root]
    return argv


def _build_project_only(
    script: Path,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> <project_root>``"""
    if not project_root:
        raise RegistryError('project_root is required')
    return [str(script), project_root]


def _build_subcommand_with_targets(
    script: Path,
    subcommand: Optional[str] = None,
    project_root: Optional[str] = None,
    targets: Optional[list[str]] = None,
    **_ignored,
) -> list[str]:
    """``<script> <subcommand> <project_root> --targets <f1> <f2>``"""
    if not subcommand:
        raise RegistryError('subcommand is required')
    if not project_root:
        raise RegistryError('project_root is required')
    argv = [str(script), subcommand, project_root]
    if targets:
        argv += ['--targets', *targets]
    return argv


def _build_ground_file(
    script: Path,
    subcommand: Optional[str] = None,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> --project-root <root> <subcommand>``"""
    if not subcommand:
        raise RegistryError('subcommand is required')
    if not project_root:
        raise RegistryError('project_root is required')
    return [str(script), '--project-root', project_root, subcommand]


def _build_work_items(
    script: Path,
    subcommand: Optional[str] = None,
    project_root: Optional[str] = None,
    epic: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> --project-root <root> <subcommand> [epic]``"""
    if not subcommand:
        raise RegistryError('subcommand is required')
    if not project_root:
        raise RegistryError('project_root is required')
    argv = [str(script), '--project-root', project_root, subcommand]
    if epic:
        argv.append(epic)
    return argv


def _build_verification_gate(
    script: Path,
    target: Optional[str] = None,
    stack: Optional[str] = None,
    security_paths: Optional[list[str]] = None,
    **_ignored,
) -> list[str]:
    """``<script> <block_file> [--stack <profile>] [--security-path ...]``"""
    if not target:
        raise RegistryError('target (verification block file) is required')
    argv = [str(script), target]
    if stack:
        argv += ['--stack', stack]
    for path in security_paths or []:
        argv += ['--security-path', path]
    return argv


def _build_review_packet(
    script: Path,
    target: Optional[str] = None,
    project_root: Optional[str] = None,
    **_ignored,
) -> list[str]:
    """``<script> check <packet> [--project-root <root>]``

    Only the ``check`` subcommand is registered. ``record`` and ``build`` are
    author-side steps that run before the reviewer exists; the orchestrator's
    job is to refuse a review whose packet was never verified.
    """
    if not target:
        raise RegistryError('target (review packet file) is required')
    argv = [str(script), 'check', target]
    if project_root:
        argv += ['--project-root', project_root]
    return argv


# --------------------------------------------------------------------------
# Registry entries
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ScriptSpec:
    """Declares one script's identity, invocation contract, and exit semantics."""

    name: str
    filename: str
    purpose: str
    lineage: str
    phases: tuple[int, ...]
    builder: Callable[..., list[str]]
    #: exit code -> suite verdict. Codes absent from the map become ERROR.
    exit_map: dict[int, str] = field(default_factory=lambda: {0: PASS, 1: FAIL})
    #: True when a FAIL from this script halts the workflow outright rather
    #: than routing to the Fix phase.
    halts_on_fail: bool = False
    requires_original: bool = False
    emits_json: bool = True

    @property
    def path(self) -> Path:
        return SCRIPT_DIR / self.filename

    def build_argv(self, **kwargs) -> list[str]:
        return self.builder(self.path, **kwargs)

    def command_string(self, **kwargs) -> str:
        return 'python3 ' + ' '.join(shlex.quote(a) for a in self.build_argv(**kwargs))

    def interpret_exit(self, code: int) -> str:
        verdict = self.exit_map.get(code, ERROR)
        if verdict == FAIL and self.halts_on_fail:
            return HALT
        return verdict


REGISTRY: dict[str, ScriptSpec] = {
    # ---- automate-dev lineage -------------------------------------------
    'orchestrator': ScriptSpec(
        name='orchestrator',
        filename='dev_orchestrator.py',
        purpose='Phase engine: analyse / test / validate / status',
        lineage='automate-dev',
        phases=(1, 4, 7),
        builder=_build_subcommand_with_targets,
    ),
    'code_review': ScriptSpec(
        name='code_review',
        filename='code_reviewer.py',
        purpose='Review with band-aid, security and breaking-change detection',
        lineage='automate-dev',
        phases=(3, 7),
        builder=_build_target_with_root,
    ),
    'simplifier': ScriptSpec(
        name='simplifier',
        filename='code_simplifier.py',
        purpose='Nesting, duplication and naming analysis',
        lineage='automate-dev',
        phases=(6,),
        builder=_build_target_with_root,
    ),
    'fix_validator': ScriptSpec(
        name='fix_validator',
        filename='fix_validator.py',
        purpose='Confirms a fix is structural, not a band-aid',
        lineage='automate-dev',
        phases=(5,),
        builder=_build_fix_validator,
        requires_original=True,
    ),
    'iteration_planner': ScriptSpec(
        name='iteration_planner',
        filename='iteration_planner.py',
        purpose='Iteration plan creation, stall detection, escalation reports',
        lineage='automate-dev',
        phases=(1, 7),
        builder=_build_subcommand_with_targets,
    ),
    'deployment_readiness': ScriptSpec(
        name='deployment_readiness',
        filename='deployment_readiness.py',
        purpose='Security, error handling and dependency pre-ship checks',
        lineage='automate-dev',
        phases=(10,),
        builder=_build_project_only,
    ),
    'token_budget': ScriptSpec(
        name='token_budget',
        filename='token_budget_monitor.py',
        purpose='Token usage tracking, budget enforcement, cost reporting',
        lineage='automate-dev',
        phases=(0,),  # cross-cutting
        builder=_build_subcommand_with_targets,
    ),

    # ---- production-code-quality lineage --------------------------------
    'breaking_changes': ScriptSpec(
        name='breaking_changes',
        filename='breaking_change_detector.py',
        purpose='Public API removal and signature change detection',
        lineage='production-code-quality',
        phases=(3, 7),
        builder=_build_two_positional,
        exit_map={0: PASS, 1: FAIL},
        halts_on_fail=True,          # breaking changes halt, never auto-fix
        requires_original=True,
    ),
    'compatibility': ScriptSpec(
        name='compatibility',
        filename='compatibility_checker.py',
        purpose='Import and signature compatibility against the project',
        lineage='production-code-quality',
        phases=(3, 7),
        builder=_build_target_then_root_positional,
    ),
    'preservation': ScriptSpec(
        name='preservation',
        filename='functionality_preserver.py',
        purpose='Feature-level functionality preservation check',
        lineage='production-code-quality',
        phases=(3, 7),
        builder=_build_two_positional,
        requires_original=True,
    ),
    'rn_analysis': ScriptSpec(
        name='rn_analysis',
        filename='rn_analyzer.py',
        purpose='React Native / Expo component, navigation and perf analysis',
        lineage='production-code-quality',
        phases=(3,),
        builder=_build_rn_analyzer,
    ),
    'self_assessment': ScriptSpec(
        name='self_assessment',
        filename='self_assessment.py',
        purpose='Consolidated self-assessment across quality dimensions',
        lineage='production-code-quality',
        phases=(7,),
        builder=_build_self_assessment,
        exit_map={0: PASS, 1: FAIL, 2: NEEDS_APPROVAL},
    ),

    # ---- suite-native ----------------------------------------------------
    'verification_gate': ScriptSpec(
        name='verification_gate',
        filename='verification_gate.py',
        purpose='Parses and enforces agent pre-output verification blocks',
        lineage='dev-automation-suite',
        phases=(2, 3, 5, 7),
        builder=_build_verification_gate,
        exit_map={0: PASS, 1: FAIL, 2: WARN},
        halts_on_fail=True,          # CONTRADICTED / security UNVERIFIED halts
    ),
    'review_packet': ScriptSpec(
        name='review_packet',
        filename='review_packet.py',
        purpose='Verifies a review packet exposes only task and completed work',
        lineage='dev-automation-suite',
        phases=(3, 7),
        builder=_build_review_packet,
        exit_map={0: PASS, 1: FAIL, 3: ERROR},
        halts_on_fail=True,   # a framed packet is not reviewable; halt, don't route
    ),
    'ground_file': ScriptSpec(
        name='ground_file',
        filename='ground_file.py',
        purpose='Tracks project premises by type and tier; flags unvalidated ones',
        lineage='common-ground',
        phases=(0, 1, 7),
        builder=_build_ground_file,
        exit_map={0: PASS, 1: FAIL, 2: WARN},
        halts_on_fail=True,   # an OPEN high-impact premise is not auto-fixable
    ),
    'work_items': ScriptSpec(
        name='work_items',
        filename='work_items.py',
        purpose='Local file-based epic/ticket tracking with dependency waves',
        lineage='project-lifecycle',
        phases=(1, 10),
        builder=_build_work_items,
        exit_map={0: PASS, 1: FAIL, 3: ERROR},
    ),
    'stack_profile': ScriptSpec(
        name='stack_profile',
        filename='stack_profile.py',
        purpose='Detects the project stack and emits the matching check profile',
        lineage='dev-automation-suite',
        phases=(1,),
        builder=_build_project_only,
    ),
}


# --------------------------------------------------------------------------
# Lookup helpers
# --------------------------------------------------------------------------

def get(name: str) -> ScriptSpec:
    """Return the spec for ``name``, raising RegistryError if unregistered."""
    try:
        return REGISTRY[name]
    except KeyError:
        known = ', '.join(sorted(REGISTRY))
        raise RegistryError(f'unknown script {name!r}; registered: {known}') from None


def for_phase(phase: int) -> list[ScriptSpec]:
    """All scripts owned by a phase, in stable registry order."""
    return [spec for spec in REGISTRY.values() if phase in spec.phases]


def requiring_original() -> list[ScriptSpec]:
    """Scripts that cannot run without a pre-change baseline file.

    The orchestrator uses this to skip diff-based checks cleanly on new files
    rather than invoking them with a missing argument and reporting ERROR.
    """
    return [spec for spec in REGISTRY.values() if spec.requires_original]


def missing_scripts() -> list[str]:
    """Filenames declared in the registry that are absent from disk.

    Called at orchestrator startup so a packaging mistake surfaces immediately
    instead of as a mid-phase failure.
    """
    return sorted(spec.filename for spec in REGISTRY.values() if not spec.path.is_file())


def _self_report() -> str:
    lines = ['Script Registry', '=' * 60]
    for spec in REGISTRY.values():
        phases = ', '.join(str(p) for p in spec.phases) or '-'
        flag = ' [HALTS]' if spec.halts_on_fail else ''
        lines.append(f'{spec.name:22} phases {phases:12} {spec.lineage}{flag}')
        lines.append(f'{"":22} {spec.purpose}')
    absent = missing_scripts()
    lines.append('')
    lines.append(f'Registered: {len(REGISTRY)}   Missing on disk: {len(absent)}')
    for name in absent:
        lines.append(f'  MISSING  {name}')
    return '\n'.join(lines)


if __name__ == '__main__':
    print(_self_report())
