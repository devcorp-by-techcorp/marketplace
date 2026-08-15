#!/usr/bin/env python3
"""
Deployment Readiness — Pre-deployment verification checks.

Validates that a project meets deployment requirements including
error handling coverage, security posture, dependency declarations,
configuration hygiene, and production server readiness.

Usage:
    python deployment_readiness.py <project_root> [--strict]
"""

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ReadinessCheck:
    """Individual deployment readiness check result."""
    name: str
    category: str
    status: str  # PASS, WARN, FAIL, SKIP
    details: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW


@dataclass
class DeploymentReadinessReport:
    """Complete deployment readiness report."""
    project_root: str
    overall_status: str  # READY, CONDITIONAL, NOT_READY
    overall_score: int
    total_checks: int
    passed: int
    warned: int
    failed: int
    skipped: int
    checks: list
    blocking_issues: list
    recommendations: list
    detected_stack: dict


def detect_stack(project_root: str) -> dict:
    """Detect the project's technology stack."""
    root = Path(project_root)
    stack = {
        'python': False,
        'flask': False,
        'node': False,
        'static_site': False,
        'has_requirements': False,
        'has_package_json': False,
        'has_dockerfile': False,
        'has_docker_compose': False,
        'has_gunicorn': False,
        'has_tests': False,
        'has_env_example': False,
        'database': None,
    }

    # Python detection
    py_files = list(root.rglob('*.py'))
    stack['python'] = len(py_files) > 0

    # Requirements
    stack['has_requirements'] = (
        (root / 'requirements.txt').exists()
        or (root / 'pyproject.toml').exists()
        or (root / 'setup.py').exists()
        or (root / 'Pipfile').exists()
    )

    # Flask detection
    for py_file in py_files[:50]:  # Check first 50 files
        try:
            with open(py_file, 'r') as f:
                content = f.read(5000)
            if 'flask' in content.lower() or 'Flask' in content:
                stack['flask'] = True
            if 'gunicorn' in content.lower():
                stack['has_gunicorn'] = True
            if 'mongoengine' in content.lower() or 'pymongo' in content.lower():
                stack['database'] = 'mongodb'
            elif 'sqlalchemy' in content.lower() or 'sqlite' in content.lower():
                stack['database'] = 'sql'
        except (PermissionError, UnicodeDecodeError):
            continue

    # Node.js detection
    stack['has_package_json'] = (root / 'package.json').exists()
    stack['node'] = stack['has_package_json'] or len(list(root.rglob('*.js'))) > 5

    # Static site detection
    index_html = (root / 'index.html').exists() or (root / 'public' / 'index.html').exists()
    stack['static_site'] = index_html and not stack['python'] and not stack['node']

    # Docker
    stack['has_dockerfile'] = (root / 'Dockerfile').exists()
    stack['has_docker_compose'] = (
        (root / 'docker-compose.yml').exists()
        or (root / 'docker-compose.yaml').exists()
    )

    # Tests
    stack['has_tests'] = (
        (root / 'tests').exists()
        or (root / 'test').exists()
        or len(list(root.rglob('test_*.py'))) > 0
        or len(list(root.rglob('*.test.js'))) > 0
        or len(list(root.rglob('*.spec.js'))) > 0
    )

    # Env example
    stack['has_env_example'] = (
        (root / '.env.example').exists()
        or (root / '.env.sample').exists()
        or (root / 'env.example').exists()
    )

    # Gunicorn in requirements
    req_path = root / 'requirements.txt'
    if req_path.exists():
        try:
            with open(req_path, 'r') as f:
                req_content = f.read().lower()
            if 'gunicorn' in req_content:
                stack['has_gunicorn'] = True
        except (PermissionError, UnicodeDecodeError):
            pass

    return stack


def check_error_handling(project_root: str, stack: dict) -> list:
    """Check error handling coverage."""
    checks = []
    root = Path(project_root)

    if not stack['python']:
        return checks

    bare_except_count = 0
    except_pass_count = 0
    total_try_blocks = 0

    py_files = list(root.rglob('*.py'))
    # Skip venv and __pycache__
    py_files = [
        f for f in py_files
        if '.venv' not in str(f)
        and 'venv' not in str(f)
        and '__pycache__' not in str(f)
        and 'node_modules' not in str(f)
    ]

    for py_file in py_files:
        try:
            with open(py_file, 'r') as f:
                content = f.read()
        except (PermissionError, UnicodeDecodeError):
            continue

        total_try_blocks += content.count('try:')
        bare_except_count += len(re.findall(r'except\s*:', content))
        except_pass_count += len(re.findall(r'except.*:\s*\n\s*pass', content))

    if bare_except_count > 0:
        checks.append(ReadinessCheck(
            name='bare_except_clauses',
            category='error_handling',
            status='FAIL',
            details=f'{bare_except_count} bare except clause(s) found — use specific exception types',
            severity='HIGH',
        ))
    else:
        checks.append(ReadinessCheck(
            name='bare_except_clauses',
            category='error_handling',
            status='PASS',
            details='No bare except clauses found',
            severity='HIGH',
        ))

    if except_pass_count > 0:
        checks.append(ReadinessCheck(
            name='except_pass_blocks',
            category='error_handling',
            status='FAIL',
            details=f'{except_pass_count} except-pass block(s) found — errors are being silently swallowed',
            severity='CRITICAL',
        ))
    else:
        checks.append(ReadinessCheck(
            name='except_pass_blocks',
            category='error_handling',
            status='PASS',
            details='No silent error swallowing detected',
            severity='CRITICAL',
        ))

    return checks


def check_security(project_root: str, stack: dict) -> list:
    """Check security posture."""
    checks = []
    root = Path(project_root)

    # Check for hardcoded secrets
    secret_patterns = [
        (r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']', 'hardcoded_password'),
        (r'(?:api_key|apikey|api_secret)\s*=\s*["\'][^"\']{8,}["\']', 'hardcoded_api_key'),
        (r'(?:secret_key|SECRET_KEY)\s*=\s*["\'][^"\']{8,}["\']', 'hardcoded_secret_key'),
        (r'(?:token|access_token)\s*=\s*["\'][^"\']{8,}["\']', 'hardcoded_token'),
    ]

    secrets_found = []
    code_files = list(root.rglob('*.py')) + list(root.rglob('*.js'))
    code_files = [
        f for f in code_files
        if '.venv' not in str(f)
        and 'venv' not in str(f)
        and '__pycache__' not in str(f)
        and 'node_modules' not in str(f)
        and '.env' not in f.name
    ]

    for code_file in code_files:
        try:
            with open(code_file, 'r') as f:
                content = f.read()
        except (PermissionError, UnicodeDecodeError):
            continue

        for pattern, name in secret_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Filter out obvious test/example values
                for match in matches:
                    if not any(
                        test_val in match.lower()
                        for test_val in ('example', 'test', 'placeholder', 'changeme', 'xxx', 'your_')
                    ):
                        secrets_found.append((str(code_file), name))

    if secrets_found:
        files = set(s[0] for s in secrets_found)
        checks.append(ReadinessCheck(
            name='hardcoded_secrets',
            category='security',
            status='FAIL',
            details=f'Potential hardcoded secrets in {len(files)} file(s) — use environment variables',
            severity='CRITICAL',
        ))
    else:
        checks.append(ReadinessCheck(
            name='hardcoded_secrets',
            category='security',
            status='PASS',
            details='No hardcoded secrets detected',
            severity='CRITICAL',
        ))

    # Check for .env file in version control
    env_file = root / '.env'
    gitignore = root / '.gitignore'
    if env_file.exists():
        env_in_gitignore = False
        if gitignore.exists():
            try:
                with open(gitignore, 'r') as f:
                    gitignore_content = f.read()
                env_in_gitignore = '.env' in gitignore_content
            except (PermissionError, UnicodeDecodeError):
                pass

        if not env_in_gitignore:
            checks.append(ReadinessCheck(
                name='env_file_exposed',
                category='security',
                status='WARN',
                details='.env file exists but may not be in .gitignore',
                severity='HIGH',
            ))

    # Check for debug mode in Flask
    if stack['flask']:
        for py_file in list(root.rglob('*.py'))[:30]:
            try:
                with open(py_file, 'r') as f:
                    content = f.read()
                if re.search(r'debug\s*=\s*True', content):
                    checks.append(ReadinessCheck(
                        name='flask_debug_mode',
                        category='security',
                        status='FAIL',
                        details='Flask debug mode is enabled — must be disabled in production',
                        severity='CRITICAL',
                    ))
                    break
            except (PermissionError, UnicodeDecodeError):
                continue

    return checks


def check_dependencies(project_root: str, stack: dict) -> list:
    """Check dependency declarations."""
    checks = []
    root = Path(project_root)

    if stack['python'] and not stack['has_requirements']:
        checks.append(ReadinessCheck(
            name='python_dependencies',
            category='dependencies',
            status='FAIL',
            details='No requirements.txt, pyproject.toml, or Pipfile found',
            severity='HIGH',
        ))
    elif stack['python']:
        checks.append(ReadinessCheck(
            name='python_dependencies',
            category='dependencies',
            status='PASS',
            details='Python dependency file found',
            severity='HIGH',
        ))

    if stack['node'] and not stack['has_package_json']:
        checks.append(ReadinessCheck(
            name='node_dependencies',
            category='dependencies',
            status='FAIL',
            details='No package.json found for Node.js project',
            severity='HIGH',
        ))
    elif stack['node'] and stack['has_package_json']:
        checks.append(ReadinessCheck(
            name='node_dependencies',
            category='dependencies',
            status='PASS',
            details='package.json found',
            severity='HIGH',
        ))

    return checks


def check_production_server(project_root: str, stack: dict) -> list:
    """Check for production-ready server configuration."""
    checks = []

    if stack['flask']:
        if stack['has_gunicorn']:
            checks.append(ReadinessCheck(
                name='production_server',
                category='server',
                status='PASS',
                details='Gunicorn detected for production serving',
                severity='HIGH',
            ))
        else:
            checks.append(ReadinessCheck(
                name='production_server',
                category='server',
                status='WARN',
                details='No production WSGI server (gunicorn) detected — Flask dev server is not production-ready',
                severity='HIGH',
            ))

    return checks


def check_testing(project_root: str, stack: dict) -> list:
    """Check test coverage presence."""
    checks = []

    if stack['has_tests']:
        checks.append(ReadinessCheck(
            name='test_suite',
            category='testing',
            status='PASS',
            details='Test directory or test files detected',
            severity='MEDIUM',
        ))
    else:
        checks.append(ReadinessCheck(
            name='test_suite',
            category='testing',
            status='WARN',
            details='No test directory or test files found',
            severity='MEDIUM',
        ))

    return checks


def check_configuration(project_root: str, stack: dict) -> list:
    """Check configuration hygiene."""
    checks = []

    if stack['has_env_example']:
        checks.append(ReadinessCheck(
            name='env_example',
            category='configuration',
            status='PASS',
            details='.env.example or equivalent found for configuration documentation',
            severity='LOW',
        ))
    elif stack['python'] or stack['node']:
        checks.append(ReadinessCheck(
            name='env_example',
            category='configuration',
            status='WARN',
            details='No .env.example found — consider documenting required environment variables',
            severity='LOW',
        ))

    return checks


def calculate_score(checks: list) -> int:
    """Calculate overall readiness score from check results."""
    if not checks:
        return 0

    score = 100
    for check in checks:
        if check.status == 'FAIL':
            if check.severity == 'CRITICAL':
                score -= 25
            elif check.severity == 'HIGH':
                score -= 15
            elif check.severity == 'MEDIUM':
                score -= 10
            else:
                score -= 5
        elif check.status == 'WARN':
            if check.severity == 'CRITICAL':
                score -= 15
            elif check.severity == 'HIGH':
                score -= 10
            elif check.severity == 'MEDIUM':
                score -= 5
            else:
                score -= 2

    return max(0, score)


def assess_readiness(project_root: str, strict: bool = False) -> DeploymentReadinessReport:
    """Run complete deployment readiness assessment."""
    stack = detect_stack(project_root)
    all_checks = []

    # Run all check categories
    all_checks.extend(check_error_handling(project_root, stack))
    all_checks.extend(check_security(project_root, stack))
    all_checks.extend(check_dependencies(project_root, stack))
    all_checks.extend(check_production_server(project_root, stack))
    all_checks.extend(check_testing(project_root, stack))
    all_checks.extend(check_configuration(project_root, stack))

    # Count results
    passed = sum(1 for c in all_checks if c.status == 'PASS')
    warned = sum(1 for c in all_checks if c.status == 'WARN')
    failed = sum(1 for c in all_checks if c.status == 'FAIL')
    skipped = sum(1 for c in all_checks if c.status == 'SKIP')

    # Calculate score
    score = calculate_score(all_checks)

    # Blocking issues
    blocking = [
        asdict(c) for c in all_checks
        if c.status == 'FAIL' and c.severity in ('CRITICAL', 'HIGH')
    ]

    # Recommendations
    recommendations = []
    for check in all_checks:
        if check.status in ('FAIL', 'WARN'):
            recommendations.append(f'[{check.severity}] {check.details}')

    # Overall status
    has_critical_fail = any(
        c.status == 'FAIL' and c.severity == 'CRITICAL'
        for c in all_checks
    )

    if strict:
        if failed > 0:
            overall = 'NOT_READY'
        elif warned > 0:
            overall = 'CONDITIONAL'
        else:
            overall = 'READY'
    else:
        if has_critical_fail:
            overall = 'NOT_READY'
        elif failed > 0:
            overall = 'CONDITIONAL'
        else:
            overall = 'READY'

    return DeploymentReadinessReport(
        project_root=project_root,
        overall_status=overall,
        overall_score=score,
        total_checks=len(all_checks),
        passed=passed,
        warned=warned,
        failed=failed,
        skipped=skipped,
        checks=[asdict(c) for c in all_checks],
        blocking_issues=blocking,
        recommendations=recommendations,
        detected_stack=stack,
    )


def main():
    parser = argparse.ArgumentParser(
        description='Deployment Readiness — pre-deployment verification'
    )
    parser.add_argument('project_root', help='Project root directory')
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Strict mode — warnings also block deployment',
    )

    args = parser.parse_args()
    report = assess_readiness(args.project_root, args.strict)
    print(json.dumps(asdict(report), indent=2))

    if report.overall_status == 'NOT_READY':
        sys.exit(1)
    elif report.overall_status == 'CONDITIONAL':
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
