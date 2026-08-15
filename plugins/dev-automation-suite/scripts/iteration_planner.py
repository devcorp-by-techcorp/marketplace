#!/usr/bin/env python3
"""
Iteration Planner — Creates and updates iteration workflow plans.

Generates structured iteration plans from task descriptions and acceptance
criteria, tracks iteration history, detects stalls and regressions, and
produces escalation reports when the workflow cannot self-resolve.

Usage:
    python iteration_planner.py create <project_root> --task "<description>" --criteria "<AC1>" "<AC2>"
    python iteration_planner.py update <project_root> --iteration <N> --status <STATUS> --scores <json>
    python iteration_planner.py check-progress <project_root>
    python iteration_planner.py escalation-report <project_root>
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class IterationEntry:
    """Single iteration record."""
    iteration: int
    timestamp: str
    phase_reached: int
    status: str  # IN_PROGRESS, PASS, FAIL
    actions_taken: list
    failures_detected: list
    root_causes_identified: list
    fixes_applied: list
    quality_scores: dict
    acceptance_progress: dict
    band_aids_detected: int = 0


@dataclass
class IterationPlan:
    """Complete iteration plan document."""
    task_description: str
    target_files: list
    existing_code: bool
    acceptance_criteria: list
    baseline_scores: dict
    iterations: list
    current_iteration: int
    overall_status: str  # IN_PROGRESS, COMPLETE, ESCALATED
    max_iterations: int
    created_at: str
    updated_at: str
    stall_window: int = 2
    fix_retry_limit: int = 3
    progress_history: list = field(default_factory=list)


def get_plan_dir(project_root: str) -> Path:
    """Get or create the .automate-dev directory."""
    plan_dir = Path(project_root) / '.automate-dev'
    plan_dir.mkdir(parents=True, exist_ok=True)
    return plan_dir


def get_plan_path(project_root: str) -> Path:
    """Get the path to the iteration plan file."""
    return get_plan_dir(project_root) / 'iteration_plan.json'


def get_markdown_path(project_root: str) -> Path:
    """Get the path to the human-readable iteration plan."""
    return get_plan_dir(project_root) / 'iteration_plan.md'


def load_plan(project_root: str) -> Optional[IterationPlan]:
    """Load existing iteration plan."""
    plan_path = get_plan_path(project_root)
    if not plan_path.exists():
        return None
    try:
        with open(plan_path, 'r') as f:
            data = json.load(f)
        return IterationPlan(**data)
    except (json.JSONDecodeError, TypeError) as e:
        print(f'Warning: Could not load plan: {e}', file=sys.stderr)
        return None


def save_plan(plan: IterationPlan, project_root: str) -> None:
    """Save iteration plan to JSON and generate markdown."""
    plan.updated_at = datetime.now().isoformat()

    # Save JSON
    plan_path = get_plan_path(project_root)
    with open(plan_path, 'w') as f:
        json.dump(asdict(plan), f, indent=2)

    # Generate markdown
    md_path = get_markdown_path(project_root)
    with open(md_path, 'w') as f:
        f.write(generate_markdown(plan))


def generate_markdown(plan: IterationPlan) -> str:
    """Generate human-readable markdown from plan data."""
    lines = []
    lines.append(f'# Iteration Plan: {plan.task_description}')
    lines.append(f'Created: {plan.created_at}')
    lines.append(f'Last Updated: {plan.updated_at}')
    lines.append('')
    lines.append('## Task Context')
    lines.append(f'- **Objective**: {plan.task_description}')
    lines.append(f'- **Target Files**: {", ".join(plan.target_files)}')
    lines.append(f'- **Existing Code**: {"YES" if plan.existing_code else "NO"}')
    lines.append(f'- **Max Iterations**: {plan.max_iterations}')
    lines.append(f'- **Overall Status**: {plan.overall_status}')
    lines.append('')

    lines.append('## Acceptance Criteria')
    for i, criterion in enumerate(plan.acceptance_criteria, 1):
        # Check if criterion is met in latest iteration
        met = False
        if plan.iterations:
            latest = plan.iterations[-1]
            progress = latest.get('acceptance_progress', {}) if isinstance(latest, dict) else {}
            met = progress.get(f'AC-{i}', False)
        checkbox = 'x' if met else ' '
        lines.append(f'- [{checkbox}] AC-{i}: {criterion}')
    lines.append('')

    if plan.baseline_scores:
        lines.append('## Baseline Scores')
        for key, value in plan.baseline_scores.items():
            lines.append(f'- {key}: {value}')
        lines.append('')

    lines.append('---')
    lines.append('')

    for iteration in plan.iterations:
        it = iteration if isinstance(iteration, dict) else asdict(iteration)
        it_num = it.get('iteration', '?')
        lines.append(f'## Iteration {it_num}')
        lines.append(f'- **Timestamp**: {it.get("timestamp", "N/A")}')
        lines.append(f'- **Phase Reached**: {it.get("phase_reached", "N/A")}')
        lines.append(f'- **Status**: {it.get("status", "N/A")}')
        lines.append('')

        actions = it.get('actions_taken', [])
        if actions:
            lines.append('**Actions Taken**:')
            for action in actions:
                lines.append(f'  - {action}')
            lines.append('')

        failures = it.get('failures_detected', [])
        if failures:
            lines.append('**Failures Detected**:')
            for failure in failures:
                lines.append(f'  - {failure}')
            lines.append('')

        root_causes = it.get('root_causes_identified', [])
        if root_causes:
            lines.append('**Root Causes Identified**:')
            for rc in root_causes:
                lines.append(f'  - {rc}')
            lines.append('')

        fixes = it.get('fixes_applied', [])
        if fixes:
            lines.append('**Fixes Applied**:')
            for fix in fixes:
                lines.append(f'  - {fix}')
            lines.append('')

        scores = it.get('quality_scores', {})
        if scores:
            lines.append('**Quality Scores**:')
            for key, value in scores.items():
                lines.append(f'  - {key}: {value}')
            band_aids = it.get('band_aids_detected', 0)
            lines.append(f'  - Band-Aids Detected: {band_aids}')
            lines.append('')

        lines.append('---')
        lines.append('')

    # Current state summary
    lines.append('## Current State')
    lines.append(f'- **Active Iteration**: {plan.current_iteration}')
    lines.append(f'- **Overall Status**: {plan.overall_status}')

    # Progress trend
    if len(plan.progress_history) >= 2:
        recent = plan.progress_history[-2:]
        if recent[-1] > recent[-2]:
            trend = 'IMPROVING'
        elif recent[-1] == recent[-2]:
            trend = 'STALLED'
        else:
            trend = 'REGRESSING'
        lines.append(f'- **Progress Trend**: {trend}')

    lines.append('')
    return '\n'.join(lines)


def detect_stall(plan: IterationPlan) -> bool:
    """Check if workflow has stalled based on progress history."""
    if len(plan.progress_history) < plan.stall_window:
        return False

    recent = plan.progress_history[-plan.stall_window:]
    return len(set(recent)) == 1


def detect_regression(plan: IterationPlan) -> bool:
    """Check if quality scores have regressed from previous iteration."""
    if len(plan.progress_history) < 2:
        return False
    return plan.progress_history[-1] < plan.progress_history[-2]


def check_fix_retry_exhausted(plan: IterationPlan) -> list:
    """Identify issues that have hit the fix retry limit."""
    exhausted = []
    failure_counts = {}

    for iteration in plan.iterations:
        it = iteration if isinstance(iteration, dict) else asdict(iteration)
        for failure in it.get('failures_detected', []):
            failure_key = str(failure)[:100]
            failure_counts[failure_key] = failure_counts.get(failure_key, 0) + 1
            if failure_counts[failure_key] >= plan.fix_retry_limit:
                if failure_key not in exhausted:
                    exhausted.append(failure_key)

    return exhausted


def generate_escalation_report(plan: IterationPlan) -> dict:
    """Generate a detailed escalation report."""
    exhausted_fixes = check_fix_retry_exhausted(plan)
    is_stalled = detect_stall(plan)
    is_regressing = detect_regression(plan)
    at_max = plan.current_iteration >= plan.max_iterations

    reasons = []
    if at_max:
        reasons.append(f'Maximum iterations ({plan.max_iterations}) reached')
    if is_stalled:
        reasons.append(f'No progress in last {plan.stall_window} iterations')
    if is_regressing:
        reasons.append('Quality scores regressing')
    if exhausted_fixes:
        reasons.append(f'{len(exhausted_fixes)} issue(s) hit retry limit')

    # Collect all attempted fixes
    all_fixes = []
    for iteration in plan.iterations:
        it = iteration if isinstance(iteration, dict) else asdict(iteration)
        for fix in it.get('fixes_applied', []):
            all_fixes.append({
                'iteration': it.get('iteration'),
                'fix': fix,
            })

    # Get latest failures
    latest_failures = []
    if plan.iterations:
        latest = plan.iterations[-1]
        it = latest if isinstance(latest, dict) else asdict(latest)
        latest_failures = it.get('failures_detected', [])

    report = {
        'escalation_type': 'AUTOMATED_WORKFLOW_ESCALATION',
        'task_description': plan.task_description,
        'total_iterations': plan.current_iteration,
        'max_iterations': plan.max_iterations,
        'escalation_reasons': reasons,
        'is_stalled': is_stalled,
        'is_regressing': is_regressing,
        'at_max_iterations': at_max,
        'exhausted_fix_retries': exhausted_fixes,
        'current_failures': latest_failures,
        'all_fixes_attempted': all_fixes,
        'progress_history': plan.progress_history,
        'acceptance_criteria': plan.acceptance_criteria,
        'recommendation': _generate_recommendation(
            is_stalled, is_regressing, at_max, exhausted_fixes, latest_failures
        ),
    }

    return report


def _generate_recommendation(
    is_stalled: bool,
    is_regressing: bool,
    at_max: bool,
    exhausted_fixes: list,
    current_failures: list,
) -> str:
    """Generate a recommendation based on escalation analysis."""
    if is_regressing:
        return (
            'Quality is regressing — recent fixes are causing new issues. '
            'Recommend reverting to the last known good state and re-approaching '
            'with a different strategy.'
        )

    if exhausted_fixes:
        return (
            f'{len(exhausted_fixes)} issue(s) could not be resolved after multiple attempts. '
            'These likely require architectural changes or user guidance on requirements. '
            'Recommend presenting the specific blocking issues to the user.'
        )

    if is_stalled:
        return (
            'Workflow has stalled with no measurable progress. '
            'The remaining issues may require a different approach or '
            'clarification of requirements from the user.'
        )

    if at_max:
        return (
            'Maximum iteration limit reached. Progress was being made but '
            'the task requires more iterations. Consider increasing the limit '
            'or breaking the task into smaller sub-tasks.'
        )

    return 'No specific recommendation — review the escalation details.'


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new iteration plan."""
    now = datetime.now().isoformat()

    # Check for existing code in target files
    existing_code = False
    for target in (args.targets or []):
        full_path = os.path.join(args.project_root, target) if not os.path.isabs(target) else target
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r') as f:
                    content = f.read().strip()
                if content:
                    existing_code = True
                    break
            except (PermissionError, UnicodeDecodeError):
                continue

    plan = IterationPlan(
        task_description=args.task,
        target_files=args.targets or [],
        existing_code=existing_code,
        acceptance_criteria=args.criteria or [],
        baseline_scores={},
        iterations=[],
        current_iteration=0,
        overall_status='IN_PROGRESS',
        max_iterations=args.max_iterations,
        created_at=now,
        updated_at=now,
        stall_window=args.stall_window,
        fix_retry_limit=args.fix_retry_limit,
        progress_history=[],
    )

    save_plan(plan, args.project_root)

    output = {
        'status': 'CREATED',
        'plan_path': str(get_plan_path(args.project_root)),
        'markdown_path': str(get_markdown_path(args.project_root)),
        'task': plan.task_description,
        'acceptance_criteria_count': len(plan.acceptance_criteria),
        'existing_code': existing_code,
    }
    print(json.dumps(output, indent=2))


def cmd_update(args: argparse.Namespace) -> None:
    """Update the iteration plan with new iteration results."""
    plan = load_plan(args.project_root)
    if plan is None:
        print(json.dumps({'error': 'No iteration plan found. Run create first.'}))
        sys.exit(1)

    # Parse scores
    scores = {}
    if args.scores:
        try:
            scores = json.loads(args.scores)
        except json.JSONDecodeError:
            scores = {}

    # Parse list arguments
    actions = args.actions or []
    failures = args.failures or []
    root_causes = args.root_causes or []
    fixes = args.fixes or []
    band_aids = args.band_aids or 0

    # Parse acceptance progress
    acceptance_progress = {}
    if args.acceptance_progress:
        try:
            acceptance_progress = json.loads(args.acceptance_progress)
        except json.JSONDecodeError:
            acceptance_progress = {}

    iteration_entry = {
        'iteration': args.iteration,
        'timestamp': datetime.now().isoformat(),
        'phase_reached': args.phase or 0,
        'status': args.status,
        'actions_taken': actions,
        'failures_detected': failures,
        'root_causes_identified': root_causes,
        'fixes_applied': fixes,
        'quality_scores': scores,
        'acceptance_progress': acceptance_progress,
        'band_aids_detected': band_aids,
    }

    plan.iterations.append(iteration_entry)
    plan.current_iteration = args.iteration

    # Track progress (use overall score if available)
    overall_score = scores.get('overall', scores.get('compatibility', 0))
    plan.progress_history.append(overall_score)

    # Update overall status
    if args.status == 'PASS':
        plan.overall_status = 'COMPLETE'
    elif plan.current_iteration >= plan.max_iterations:
        plan.overall_status = 'ESCALATED'
    elif detect_stall(plan):
        plan.overall_status = 'ESCALATED'

    save_plan(plan, args.project_root)

    output = {
        'status': 'UPDATED',
        'iteration': args.iteration,
        'iteration_status': args.status,
        'overall_status': plan.overall_status,
        'is_stalled': detect_stall(plan),
        'is_regressing': detect_regression(plan),
    }
    print(json.dumps(output, indent=2))


def cmd_check_progress(args: argparse.Namespace) -> None:
    """Check current workflow progress and detect issues."""
    plan = load_plan(args.project_root)
    if plan is None:
        print(json.dumps({'error': 'No iteration plan found.'}))
        sys.exit(1)

    is_stalled = detect_stall(plan)
    is_regressing = detect_regression(plan)
    exhausted = check_fix_retry_exhausted(plan)

    # Calculate acceptance criteria progress
    criteria_met = 0
    if plan.iterations:
        latest = plan.iterations[-1]
        it = latest if isinstance(latest, dict) else {}
        progress = it.get('acceptance_progress', {})
        criteria_met = sum(1 for v in progress.values() if v)

    output = {
        'overall_status': plan.overall_status,
        'current_iteration': plan.current_iteration,
        'max_iterations': plan.max_iterations,
        'iterations_remaining': plan.max_iterations - plan.current_iteration,
        'is_stalled': is_stalled,
        'is_regressing': is_regressing,
        'exhausted_fix_retries': exhausted,
        'acceptance_criteria_met': criteria_met,
        'acceptance_criteria_total': len(plan.acceptance_criteria),
        'progress_history': plan.progress_history,
        'needs_escalation': is_stalled or is_regressing or len(exhausted) > 0,
    }
    print(json.dumps(output, indent=2))

    if output['needs_escalation']:
        sys.exit(2)


def cmd_escalation_report(args: argparse.Namespace) -> None:
    """Generate an escalation report."""
    plan = load_plan(args.project_root)
    if plan is None:
        print(json.dumps({'error': 'No iteration plan found.'}))
        sys.exit(1)

    report = generate_escalation_report(plan)
    print(json.dumps(report, indent=2))

    # Also write a markdown escalation report
    report_path = get_plan_dir(args.project_root) / 'escalation_report.md'
    with open(report_path, 'w') as f:
        f.write('# Development Workflow Escalation\n\n')
        f.write(f'**Task**: {report["task_description"]}\n')
        f.write(f'**Iterations**: {report["total_iterations"]}/{report["max_iterations"]}\n\n')
        f.write('## Escalation Reasons\n')
        for reason in report['escalation_reasons']:
            f.write(f'- {reason}\n')
        f.write(f'\n## Recommendation\n{report["recommendation"]}\n\n')
        f.write('## Current Failures\n')
        for failure in report['current_failures']:
            f.write(f'- {failure}\n')
        f.write('\n## All Fix Attempts\n')
        for fix in report['all_fixes_attempted']:
            f.write(f'- Iteration {fix["iteration"]}: {fix["fix"]}\n')


def main():
    parser = argparse.ArgumentParser(
        description='Iteration Planner — create and manage iteration workflow plans'
    )
    subparsers = parser.add_subparsers(dest='command', help='Planner command')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new iteration plan')
    create_parser.add_argument('project_root', help='Project root directory')
    create_parser.add_argument('--task', required=True, help='Task description')
    create_parser.add_argument('--targets', nargs='+', help='Target files')
    create_parser.add_argument('--criteria', nargs='+', help='Acceptance criteria')
    create_parser.add_argument('--max-iterations', type=int, default=10, help='Max iterations')
    create_parser.add_argument('--stall-window', type=int, default=2, help='Stall detection window')
    create_parser.add_argument('--fix-retry-limit', type=int, default=3, help='Fix retry limit per issue')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update plan with iteration results')
    update_parser.add_argument('project_root', help='Project root directory')
    update_parser.add_argument('--iteration', type=int, required=True, help='Iteration number')
    update_parser.add_argument('--status', required=True, choices=['IN_PROGRESS', 'PASS', 'FAIL'])
    update_parser.add_argument('--phase', type=int, help='Phase reached (1-8)')
    update_parser.add_argument('--scores', help='Quality scores as JSON string')
    update_parser.add_argument('--actions', nargs='+', help='Actions taken')
    update_parser.add_argument('--failures', nargs='+', help='Failures detected')
    update_parser.add_argument('--root-causes', nargs='+', help='Root causes identified')
    update_parser.add_argument('--fixes', nargs='+', help='Fixes applied')
    update_parser.add_argument('--band-aids', type=int, default=0, help='Band-aid patterns detected')
    update_parser.add_argument('--acceptance-progress', help='Acceptance progress as JSON string')

    # Check progress command
    progress_parser = subparsers.add_parser('check-progress', help='Check workflow progress')
    progress_parser.add_argument('project_root', help='Project root directory')

    # Escalation report command
    escalation_parser = subparsers.add_parser('escalation-report', help='Generate escalation report')
    escalation_parser.add_argument('project_root', help='Project root directory')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        'create': cmd_create,
        'update': cmd_update,
        'check-progress': cmd_check_progress,
        'escalation-report': cmd_escalation_report,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
