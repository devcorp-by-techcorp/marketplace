#!/usr/bin/env python3
"""
Development Orchestrator — Main workflow engine for automate-dev skill.

Coordinates the full build-review-test-fix-simplify-validate loop.
Tracks iteration state and enforces quality gates.

Usage:
    python dev_orchestrator.py analyse <project_root> --targets <file1> [<file2> ...]
    python dev_orchestrator.py test <project_root> --targets <file1> [<file2> ...]
    python dev_orchestrator.py validate <project_root> --targets <file1> [<file2> ...]
    python dev_orchestrator.py status <project_root>
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PhaseResult:
    """Result from a single workflow phase."""
    phase: str
    status: str  # PASS, WARN, FAIL, HALT
    score: Optional[int]
    details: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class IterationResult:
    """Result from a complete iteration."""
    iteration: int
    phase_results: list
    overall_status: str
    overall_score: int
    failures: list
    fixes_applied: list
    acceptance_progress: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class WorkflowState:
    """Persistent state for the development workflow."""
    task_description: str
    target_files: list
    project_root: str
    max_iterations: int
    current_iteration: int
    iterations: list
    acceptance_criteria: list
    baseline_scores: dict
    status: str  # IN_PROGRESS, COMPLETE, ESCALATED, HALTED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


def get_state_dir(project_root: str) -> Path:
    """Get or create the .automate-dev state directory."""
    state_dir = Path(project_root) / '.automate-dev'
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def load_state(project_root: str) -> Optional[WorkflowState]:
    """Load existing workflow state if present."""
    state_file = get_state_dir(project_root) / 'state.json'
    if not state_file.exists():
        return None
    try:
        with open(state_file, 'r') as f:
            data = json.load(f)
        return WorkflowState(**data)
    except (json.JSONDecodeError, TypeError) as e:
        print(f'Warning: Could not load state: {e}', file=sys.stderr)
        return None


def save_state(state: WorkflowState) -> None:
    """Persist workflow state to disk."""
    state.updated_at = datetime.now().isoformat()
    state_file = get_state_dir(state.project_root) / 'state.json'
    with open(state_file, 'w') as f:
        json.dump(asdict(state), f, indent=2)


def inventory_file(filepath: str) -> dict:
    """Catalogue functions, classes, imports, and exports in a file."""
    inventory = {
        'filepath': filepath,
        'functions': [],
        'classes': [],
        'imports': [],
        'exports': [],
        'routes': [],
        'constants': [],
        'line_count': 0,
        'has_main': False,
    }

    try:
        with open(filepath, 'r') as f:
            content = f.read()
            lines = content.split('\n')
    except (FileNotFoundError, PermissionError) as e:
        inventory['error'] = str(e)
        return inventory

    inventory['line_count'] = len(lines)

    import re

    # Python function definitions
    for match in re.finditer(r'^(async\s+)?def\s+(\w+)\s*\((.*?)\)', content, re.MULTILINE):
        is_async = bool(match.group(1))
        name = match.group(2)
        params = match.group(3).strip()
        inventory['functions'].append({
            'name': name,
            'params': params,
            'async': is_async,
            'line': content[:match.start()].count('\n') + 1,
        })

    # Python class definitions
    for match in re.finditer(r'^class\s+(\w+)\s*(?:\((.*?)\))?:', content, re.MULTILINE):
        name = match.group(1)
        bases = match.group(2) or ''
        inventory['classes'].append({
            'name': name,
            'bases': bases.strip(),
            'line': content[:match.start()].count('\n') + 1,
        })

    # Import statements
    for match in re.finditer(r'^(?:from\s+(\S+)\s+)?import\s+(.+)$', content, re.MULTILINE):
        from_module = match.group(1) or ''
        imported = match.group(2).strip()
        inventory['imports'].append({
            'from': from_module,
            'import': imported,
            'line': content[:match.start()].count('\n') + 1,
        })

    # Flask route decorators
    for match in re.finditer(r'@\w+\.route\([\'"](.+?)[\'"]\s*(?:,\s*methods=\[(.+?)\])?\)', content):
        route = match.group(1)
        methods = match.group(2) or "'GET'"
        inventory['routes'].append({
            'path': route,
            'methods': methods,
            'line': content[:match.start()].count('\n') + 1,
        })

    # Module-level constants (UPPER_CASE assignments)
    for match in re.finditer(r'^([A-Z][A-Z0-9_]+)\s*=', content, re.MULTILINE):
        inventory['constants'].append({
            'name': match.group(1),
            'line': content[:match.start()].count('\n') + 1,
        })

    # Check for __main__ block
    inventory['has_main'] = "if __name__ ==" in content

    # JavaScript/HTML analysis (basic)
    if filepath.endswith(('.js', '.html', '.htm')):
        for match in re.finditer(r'function\s+(\w+)\s*\((.*?)\)', content):
            inventory['functions'].append({
                'name': match.group(1),
                'params': match.group(2).strip(),
                'async': False,
                'line': content[:match.start()].count('\n') + 1,
            })

    return inventory


def find_dependents(filepath: str, project_root: str) -> list:
    """Find files that import from the target file."""
    dependents = []
    target_module = Path(filepath).stem
    target_path = Path(filepath)

    for root_dir, dirs, files in os.walk(project_root):
        # Skip hidden dirs, venv, __pycache__, node_modules
        dirs[:] = [
            d for d in dirs
            if not d.startswith('.') and d not in ('__pycache__', 'node_modules', '.venv', 'venv')
        ]

        for filename in files:
            if not filename.endswith(('.py', '.js', '.html', '.htm')):
                continue

            full_path = Path(root_dir) / filename
            if full_path.resolve() == target_path.resolve():
                continue

            try:
                with open(full_path, 'r') as f:
                    content = f.read()
                if target_module in content:
                    dependents.append({
                        'file': str(full_path),
                        'references': content.count(target_module),
                    })
            except (PermissionError, UnicodeDecodeError):
                continue

    return dependents


def run_script(script_name: str, args: list) -> dict:
    """Run a sibling script and return parsed JSON output."""
    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        return {'error': f'Script not found: {script_name}', 'status': 'ERROR'}

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)] + args,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {
                    'status': 'ERROR',
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                }
        return {
            'status': 'ERROR',
            'returncode': result.returncode,
            'stderr': result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {'status': 'ERROR', 'error': 'Script timed out after 120s'}
    except Exception as e:
        return {'status': 'ERROR', 'error': str(e)}


def phase_analyse(project_root: str, target_files: list) -> PhaseResult:
    """Execute Phase 1: Analyse — inventory and dependency mapping."""
    analysis = {
        'inventories': {},
        'dependency_map': {},
        'total_functions': 0,
        'total_classes': 0,
        'total_routes': 0,
    }

    for filepath in target_files:
        full_path = os.path.join(project_root, filepath) if not os.path.isabs(filepath) else filepath

        # Inventory the file
        inv = inventory_file(full_path)
        analysis['inventories'][filepath] = inv
        analysis['total_functions'] += len(inv['functions'])
        analysis['total_classes'] += len(inv['classes'])
        analysis['total_routes'] += len(inv['routes'])

        # Find dependents
        dependents = find_dependents(full_path, project_root)
        analysis['dependency_map'][filepath] = {
            'imports': inv['imports'],
            'imported_by': dependents,
        }

    return PhaseResult(
        phase='analyse',
        status='PASS',
        score=100,
        details=analysis,
    )


def phase_review(project_root: str, target_files: list) -> PhaseResult:
    """Execute Phase 3: Review — run code reviewer on all targets."""
    results = {}
    overall_score = 100
    has_failure = False
    has_halt = False

    for filepath in target_files:
        full_path = os.path.join(project_root, filepath) if not os.path.isabs(filepath) else filepath
        review = run_script('code_reviewer.py', [full_path, '--project-root', project_root])
        results[filepath] = review

        file_score = review.get('overall_score', 0)
        overall_score = min(overall_score, file_score)

        if review.get('breaking_changes_detected', False):
            has_halt = True
        if review.get('band_aids_detected', 0) > 0:
            has_failure = True
        if review.get('overall_status') == 'FAIL':
            has_failure = True

    status = 'HALT' if has_halt else ('FAIL' if has_failure else ('PASS' if overall_score >= 95 else 'WARN'))

    return PhaseResult(
        phase='review',
        status=status,
        score=overall_score,
        details=results,
    )


def phase_test(project_root: str, target_files: list) -> PhaseResult:
    """Execute Phase 4: Test — run available test suites."""
    test_results = {
        'unit_tests': {'status': 'SKIPPED', 'details': 'No test runner detected'},
        'files_checked': target_files,
    }

    # Detect and run Python tests
    pytest_ini = Path(project_root) / 'pytest.ini'
    setup_cfg = Path(project_root) / 'setup.cfg'
    pyproject = Path(project_root) / 'pyproject.toml'
    tests_dir = Path(project_root) / 'tests'

    has_pytest = pytest_ini.exists() or setup_cfg.exists() or pyproject.exists() or tests_dir.exists()

    if has_pytest:
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pytest', '--tb=short', '-q', project_root],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=project_root,
            )
            test_results['unit_tests'] = {
                'status': 'PASS' if result.returncode == 0 else 'FAIL',
                'output': result.stdout[-2000:] if result.stdout else '',
                'errors': result.stderr[-1000:] if result.stderr else '',
                'returncode': result.returncode,
            }
        except subprocess.TimeoutExpired:
            test_results['unit_tests'] = {
                'status': 'FAIL',
                'error': 'Test suite timed out after 300s',
            }

    # Detect and run Node.js tests
    package_json = Path(project_root) / 'package.json'
    if package_json.exists():
        try:
            with open(package_json, 'r') as f:
                pkg = json.load(f)
            if 'test' in pkg.get('scripts', {}):
                result = subprocess.run(
                    ['npm', 'test', '--', '--ci'],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=project_root,
                )
                test_results['npm_tests'] = {
                    'status': 'PASS' if result.returncode == 0 else 'FAIL',
                    'output': result.stdout[-2000:] if result.stdout else '',
                }
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Determine overall test status
    statuses = [v.get('status', 'SKIPPED') for v in test_results.values() if isinstance(v, dict)]
    has_fail = 'FAIL' in statuses
    has_pass = 'PASS' in statuses
    all_skipped = all(s == 'SKIPPED' for s in statuses)

    if has_fail:
        overall = 'FAIL'
        score = 0
    elif all_skipped:
        overall = 'WARN'
        score = 50
    else:
        overall = 'PASS'
        score = 100

    return PhaseResult(
        phase='test',
        status=overall,
        score=score,
        details=test_results,
    )


def phase_validate(project_root: str, target_files: list) -> PhaseResult:
    """Execute Phase 7: Validate — final quality gate check."""
    validation = {
        'review': None,
        'tests': None,
        'fix_validation': {},
        'deployment_readiness': None,
    }

    # Run review
    review_result = phase_review(project_root, target_files)
    validation['review'] = asdict(review_result)

    # Run tests
    test_result = phase_test(project_root, target_files)
    validation['tests'] = asdict(test_result)

    # Run fix validation on each file
    for filepath in target_files:
        full_path = os.path.join(project_root, filepath) if not os.path.isabs(filepath) else filepath
        fix_result = run_script('fix_validator.py', [full_path, full_path, '--project-root', project_root])
        validation['fix_validation'][filepath] = fix_result

    # Run deployment readiness
    deploy_result = run_script('deployment_readiness.py', [project_root])
    validation['deployment_readiness'] = deploy_result

    # Calculate overall status
    statuses = [
        review_result.status,
        test_result.status,
    ]

    for fix_res in validation['fix_validation'].values():
        if fix_res.get('band_aids_found', 0) > 0:
            statuses.append('FAIL')

    if 'HALT' in statuses:
        overall = 'HALT'
    elif 'FAIL' in statuses:
        overall = 'FAIL'
    elif 'WARN' in statuses:
        overall = 'CONDITIONAL_PASS'
    else:
        overall = 'PASS'

    scores = [review_result.score or 0, test_result.score or 0]
    overall_score = sum(scores) // len(scores) if scores else 0

    return PhaseResult(
        phase='validate',
        status=overall,
        score=overall_score,
        details=validation,
    )


def detect_stall(iterations: list, window: int = 2) -> bool:
    """Detect if workflow has stalled (no progress in recent iterations)."""
    if len(iterations) < window:
        return False

    recent = iterations[-window:]
    scores = [it.get('overall_score', 0) if isinstance(it, dict) else 0 for it in recent]

    # Stalled if all scores are identical
    return len(set(scores)) == 1


def cmd_analyse(args: argparse.Namespace) -> None:
    """Handle the 'analyse' command."""
    result = phase_analyse(args.project_root, args.targets)
    output = asdict(result)
    print(json.dumps(output, indent=2))

    # Save initial state
    state = WorkflowState(
        task_description=f'Analysis of {", ".join(args.targets)}',
        target_files=args.targets,
        project_root=args.project_root,
        max_iterations=args.max_iterations,
        current_iteration=0,
        iterations=[],
        acceptance_criteria=[],
        baseline_scores={
            'total_functions': result.details['total_functions'],
            'total_classes': result.details['total_classes'],
            'total_routes': result.details['total_routes'],
        },
        status='IN_PROGRESS',
    )
    save_state(state)


def cmd_test(args: argparse.Namespace) -> None:
    """Handle the 'test' command."""
    result = phase_test(args.project_root, args.targets)
    print(json.dumps(asdict(result), indent=2))
    sys.exit(0 if result.status == 'PASS' else 1)


def cmd_validate(args: argparse.Namespace) -> None:
    """Handle the 'validate' command."""
    result = phase_validate(args.project_root, args.targets)
    output = asdict(result)
    print(json.dumps(output, indent=2))

    # Update state
    state = load_state(args.project_root)
    if state:
        state.current_iteration += 1
        iteration_data = {
            'iteration': state.current_iteration,
            'overall_status': result.status,
            'overall_score': result.score,
            'timestamp': result.timestamp,
            'details': result.details,
        }
        state.iterations.append(iteration_data)

        if result.status in ('PASS', 'CONDITIONAL_PASS'):
            state.status = 'COMPLETE'
        elif state.current_iteration >= state.max_iterations:
            state.status = 'ESCALATED'
        elif detect_stall(state.iterations):
            state.status = 'ESCALATED'

        save_state(state)

    sys.exit(0 if result.status in ('PASS', 'CONDITIONAL_PASS') else 1)


def cmd_status(args: argparse.Namespace) -> None:
    """Handle the 'status' command."""
    state = load_state(args.project_root)
    if state is None:
        print(json.dumps({'error': 'No workflow state found'}, indent=2))
        sys.exit(1)

    summary = {
        'status': state.status,
        'current_iteration': state.current_iteration,
        'max_iterations': state.max_iterations,
        'target_files': state.target_files,
        'iterations_summary': [],
    }

    for it in state.iterations:
        summary['iterations_summary'].append({
            'iteration': it.get('iteration'),
            'status': it.get('overall_status'),
            'score': it.get('overall_score'),
            'timestamp': it.get('timestamp'),
        })

    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description='Development Orchestrator — automate-dev workflow engine'
    )
    subparsers = parser.add_subparsers(dest='command', help='Workflow command')

    # Analyse command
    analyse_parser = subparsers.add_parser('analyse', help='Analyse target files')
    analyse_parser.add_argument('project_root', help='Project root directory')
    analyse_parser.add_argument('--targets', nargs='+', required=True, help='Target files')
    analyse_parser.add_argument('--max-iterations', type=int, default=10, help='Max loop iterations')

    # Test command
    test_parser = subparsers.add_parser('test', help='Run tests')
    test_parser.add_argument('project_root', help='Project root directory')
    test_parser.add_argument('--targets', nargs='+', required=True, help='Target files')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Run full validation')
    validate_parser.add_argument('project_root', help='Project root directory')
    validate_parser.add_argument('--targets', nargs='+', required=True, help='Target files')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show workflow status')
    status_parser.add_argument('project_root', help='Project root directory')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        'analyse': cmd_analyse,
        'test': cmd_test,
        'validate': cmd_validate,
        'status': cmd_status,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
