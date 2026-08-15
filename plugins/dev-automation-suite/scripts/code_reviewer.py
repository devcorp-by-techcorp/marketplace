#!/usr/bin/env python3
"""
Code Reviewer — Automated code review with band-aid detection.

Checks for breaking changes, functionality preservation, code quality,
security issues, and band-aid fix patterns.

Usage:
    python code_reviewer.py <file> --project-root <root> [--original <original_file>]
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# Band-aid detection patterns with descriptions
BAND_AID_PATTERNS = [
    {
        'pattern': r'except\s*:\s*pass',
        'name': 'bare_except_pass',
        'severity': 'CRITICAL',
        'description': 'Bare except with pass — swallows all errors silently',
    },
    {
        'pattern': r'except\s+\w+(?:\s+as\s+\w+)?\s*:\s*pass',
        'name': 'typed_except_pass',
        'severity': 'HIGH',
        'description': 'Typed except with pass — silently ignores specific errors',
    },
    {
        'pattern': r'except\s+.*:\s*return\s+None\s*$',
        'name': 'except_return_none',
        'severity': 'HIGH',
        'description': 'Exception returns None — masks failure as missing data',
    },
    {
        'pattern': r'#\s*noqa\b',
        'name': 'noqa_suppression',
        'severity': 'MEDIUM',
        'description': 'Lint suppression — hides code quality issues',
    },
    {
        'pattern': r'#\s*type:\s*ignore',
        'name': 'type_ignore',
        'severity': 'MEDIUM',
        'description': 'Type suppression — hides type safety issues',
    },
    {
        'pattern': r'#\s*pylint:\s*disable',
        'name': 'pylint_disable',
        'severity': 'MEDIUM',
        'description': 'Pylint suppression — hides linting issues',
    },
    {
        'pattern': r'#\s*(?:TODO|FIXME|HACK|XXX).*(?:workaround|temporary|temp fix|band.?aid)',
        'name': 'acknowledged_workaround',
        'severity': 'CRITICAL',
        'description': 'Explicitly acknowledged workaround in comments',
    },
    {
        'pattern': r'timeout\s*=\s*9{3,}',
        'name': 'absurd_timeout',
        'severity': 'HIGH',
        'description': 'Absurdly high timeout — masks timing issues',
    },
    {
        'pattern': r'(?:max_retries|retry_count|retries)\s*=\s*(?:[5-9]\d+|\d{3,})',
        'name': 'excessive_retries',
        'severity': 'HIGH',
        'description': 'Excessive retry count — masks intermittent failures',
    },
    {
        'pattern': r'except\s*:\s*\n\s*(?:continue|return\b)',
        'name': 'except_continue',
        'severity': 'HIGH',
        'description': 'Bare except with continue/return — skips errors silently',
    },
]

# Security issue patterns
SECURITY_PATTERNS = [
    {
        'pattern': r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
        'name': 'hardcoded_secret',
        'severity': 'CRITICAL',
        'description': 'Hardcoded credential or secret',
    },
    {
        'pattern': r'eval\s*\(',
        'name': 'eval_usage',
        'severity': 'HIGH',
        'description': 'Use of eval() — potential code injection',
    },
    {
        'pattern': r'exec\s*\(',
        'name': 'exec_usage',
        'severity': 'HIGH',
        'description': 'Use of exec() — potential code injection',
    },
    {
        'pattern': r'subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True',
        'name': 'shell_injection',
        'severity': 'HIGH',
        'description': 'Shell=True in subprocess — potential command injection',
    },
    {
        'pattern': r'\.format\s*\(.*\)\s*.*(?:SELECT|INSERT|UPDATE|DELETE|DROP)',
        'name': 'sql_injection',
        'severity': 'CRITICAL',
        'description': 'String formatting in SQL — potential SQL injection',
    },
    {
        'pattern': r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)',
        'name': 'sql_fstring_injection',
        'severity': 'CRITICAL',
        'description': 'F-string in SQL query — potential SQL injection',
    },
]


@dataclass
class ReviewFinding:
    """Individual review finding."""
    category: str
    severity: str
    name: str
    description: str
    line: Optional[int] = None
    context: Optional[str] = None


@dataclass
class CodeReviewReport:
    """Complete code review report."""
    filepath: str
    overall_status: str
    overall_score: int
    breaking_changes_detected: bool
    band_aids_detected: int
    security_issues_detected: int
    quality_issues: list
    findings: list
    function_count: int
    class_count: int
    line_count: int
    complexity_warnings: list


def analyse_complexity(content: str) -> list:
    """Analyse function complexity based on nesting depth and branch count."""
    warnings = []
    lines = content.split('\n')

    # Track function boundaries and nesting
    current_function = None
    function_start = 0
    max_depth = 0
    branch_count = 0
    current_depth = 0

    branch_keywords = {'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'with'}

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect function definition
        func_match = re.match(r'^(?:async\s+)?def\s+(\w+)', stripped)
        if func_match:
            # Save previous function analysis
            if current_function and (max_depth > 4 or branch_count > 10):
                complexity = branch_count + 1
                warnings.append({
                    'function': current_function,
                    'line': function_start,
                    'complexity': complexity,
                    'max_nesting': max_depth,
                    'branches': branch_count,
                    'status': 'FAIL' if complexity > 15 else ('WARN' if complexity > 10 else 'PASS'),
                })

            current_function = func_match.group(1)
            function_start = i
            max_depth = 0
            branch_count = 0
            current_depth = 0
            continue

        if current_function and stripped:
            # Calculate indentation depth
            indent = len(line) - len(line.lstrip())
            depth = indent // 4  # Assuming 4-space indent
            max_depth = max(max_depth, depth)

            # Count branches
            first_word = stripped.split('(')[0].split(':')[0].split(' ')[0]
            if first_word in branch_keywords:
                branch_count += 1

    # Handle last function
    if current_function and (max_depth > 4 or branch_count > 10):
        complexity = branch_count + 1
        warnings.append({
            'function': current_function,
            'line': function_start,
            'complexity': complexity,
            'max_nesting': max_depth,
            'branches': branch_count,
            'status': 'FAIL' if complexity > 15 else ('WARN' if complexity > 10 else 'PASS'),
        })

    return warnings


def detect_band_aids(content: str) -> list:
    """Detect band-aid fix patterns in code."""
    findings = []
    lines = content.split('\n')

    for pattern_def in BAND_AID_PATTERNS:
        for i, line in enumerate(lines, 1):
            if re.search(pattern_def['pattern'], line, re.IGNORECASE):
                findings.append(ReviewFinding(
                    category='band_aid',
                    severity=pattern_def['severity'],
                    name=pattern_def['name'],
                    description=pattern_def['description'],
                    line=i,
                    context=line.strip()[:100],
                ))

    return findings


def detect_security_issues(content: str) -> list:
    """Detect security issue patterns in code."""
    findings = []
    lines = content.split('\n')

    for pattern_def in SECURITY_PATTERNS:
        for i, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue

            if re.search(pattern_def['pattern'], line, re.IGNORECASE):
                findings.append(ReviewFinding(
                    category='security',
                    severity=pattern_def['severity'],
                    name=pattern_def['name'],
                    description=pattern_def['description'],
                    line=i,
                    context=line.strip()[:80],
                ))

    return findings


def check_quality(content: str, filepath: str) -> list:
    """Check general code quality issues."""
    issues = []
    lines = content.split('\n')

    # Check for bare except (not pass — that's band-aid detection)
    for i, line in enumerate(lines, 1):
        if re.match(r'\s*except\s*:', line) and 'pass' not in lines[i] if i < len(lines) else True:
            issues.append({
                'type': 'bare_except',
                'line': i,
                'message': 'Bare except clause — use specific exception types',
            })

    # Check for TODO/FIXME in production code
    todo_count = 0
    for i, line in enumerate(lines, 1):
        if re.search(r'#\s*(?:TODO|FIXME)\b', line, re.IGNORECASE):
            todo_count += 1
    if todo_count > 0:
        issues.append({
            'type': 'todos_present',
            'count': todo_count,
            'message': f'{todo_count} TODO/FIXME comments in deliverable code',
        })

    # Check file length
    if len(lines) > 500:
        issues.append({
            'type': 'file_too_long',
            'lines': len(lines),
            'message': f'File has {len(lines)} lines (target: ≤500)',
        })

    # Check for missing docstrings on public functions
    undocumented = 0
    total_public = 0
    for i, line in enumerate(lines):
        func_match = re.match(r'^(?:async\s+)?def\s+(\w+)', line.strip())
        if func_match and not func_match.group(1).startswith('_'):
            total_public += 1
            # Check next non-empty line for docstring
            next_line_idx = i + 1
            while next_line_idx < len(lines) and not lines[next_line_idx].strip():
                next_line_idx += 1
            if next_line_idx < len(lines):
                next_line = lines[next_line_idx].strip()
                if not (next_line.startswith('"""') or next_line.startswith("'''")):
                    undocumented += 1

    if undocumented > 0:
        issues.append({
            'type': 'missing_docstrings',
            'undocumented': undocumented,
            'total_public': total_public,
            'message': f'{undocumented}/{total_public} public functions lack docstrings',
        })

    return issues


def detect_breaking_changes(original_content: str, modified_content: str) -> list:
    """Detect breaking changes between original and modified code."""
    changes = []

    # Extract function signatures
    def extract_functions(content):
        funcs = {}
        for match in re.finditer(r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)', content, re.MULTILINE):
            name = match.group(1)
            params = match.group(2).strip()
            funcs[name] = params
        return funcs

    # Extract class definitions
    def extract_classes(content):
        classes = {}
        for match in re.finditer(r'^class\s+(\w+)', content, re.MULTILINE):
            classes[match.group(1)] = True
        return classes

    orig_funcs = extract_functions(original_content)
    mod_funcs = extract_functions(modified_content)
    orig_classes = extract_classes(original_content)
    mod_classes = extract_classes(modified_content)

    # Check for removed functions
    for name in orig_funcs:
        if name not in mod_funcs:
            changes.append({
                'type': 'removed_function',
                'symbol': name,
                'severity': 'CRITICAL',
                'impact': f'Function {name}() has been removed',
            })
        elif orig_funcs[name] != mod_funcs[name]:
            changes.append({
                'type': 'changed_signature',
                'symbol': name,
                'severity': 'HIGH',
                'original': orig_funcs[name],
                'modified': mod_funcs[name],
                'impact': f'Function {name}() signature changed',
            })

    # Check for removed classes
    for name in orig_classes:
        if name not in mod_classes:
            changes.append({
                'type': 'removed_class',
                'symbol': name,
                'severity': 'CRITICAL',
                'impact': f'Class {name} has been removed',
            })

    return changes


def review_file(
    filepath: str,
    project_root: str,
    original_filepath: Optional[str] = None,
) -> CodeReviewReport:
    """Run complete code review on a file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except (FileNotFoundError, PermissionError) as e:
        return CodeReviewReport(
            filepath=filepath,
            overall_status='ERROR',
            overall_score=0,
            breaking_changes_detected=False,
            band_aids_detected=0,
            security_issues_detected=0,
            quality_issues=[],
            findings=[{'error': str(e)}],
            function_count=0,
            class_count=0,
            line_count=0,
            complexity_warnings=[],
        )

    lines = content.split('\n')
    all_findings = []

    # Band-aid detection
    band_aid_findings = detect_band_aids(content)
    all_findings.extend(band_aid_findings)

    # Security detection
    security_findings = detect_security_issues(content)
    all_findings.extend(security_findings)

    # Quality checks
    quality_issues = check_quality(content, filepath)

    # Complexity analysis
    complexity_warnings = analyse_complexity(content)

    # Breaking change detection
    breaking_changes = []
    if original_filepath:
        try:
            with open(original_filepath, 'r') as f:
                original_content = f.read()
            breaking_changes = detect_breaking_changes(original_content, content)
        except (FileNotFoundError, PermissionError):
            pass

    # Count functions and classes
    func_count = len(re.findall(r'^(?:async\s+)?def\s+\w+', content, re.MULTILINE))
    class_count = len(re.findall(r'^class\s+\w+', content, re.MULTILINE))

    # Calculate score
    score = 100

    # Band-aid penalties
    for finding in band_aid_findings:
        if finding.severity == 'CRITICAL':
            score -= 25
        elif finding.severity == 'HIGH':
            score -= 15
        else:
            score -= 10

    # Security penalties
    for finding in security_findings:
        if finding.severity == 'CRITICAL':
            score -= 20
        elif finding.severity == 'HIGH':
            score -= 10

    # Quality penalties
    for issue in quality_issues:
        if issue['type'] == 'bare_except':
            score -= 10
        elif issue['type'] == 'file_too_long':
            score -= 5
        elif issue['type'] == 'missing_docstrings':
            score -= 5

    # Complexity penalties
    for warning in complexity_warnings:
        if warning['status'] == 'FAIL':
            score -= 15
        elif warning['status'] == 'WARN':
            score -= 5

    score = max(0, score)

    # Determine overall status
    has_breaking = len(breaking_changes) > 0
    has_band_aids = len(band_aid_findings) > 0
    has_critical_security = any(f.severity == 'CRITICAL' for f in security_findings)

    if has_breaking:
        overall_status = 'HALT'
    elif has_band_aids or has_critical_security:
        overall_status = 'FAIL'
    elif score >= 80:
        overall_status = 'PASS'
    elif score >= 65:
        overall_status = 'WARN'
    else:
        overall_status = 'FAIL'

    return CodeReviewReport(
        filepath=filepath,
        overall_status=overall_status,
        overall_score=score,
        breaking_changes_detected=has_breaking,
        band_aids_detected=len(band_aid_findings),
        security_issues_detected=len(security_findings),
        quality_issues=quality_issues,
        findings=[asdict(f) for f in all_findings] + [
            {'category': 'breaking_change', **bc} for bc in breaking_changes
        ],
        function_count=func_count,
        class_count=class_count,
        line_count=len(lines),
        complexity_warnings=complexity_warnings,
    )


def main():
    parser = argparse.ArgumentParser(description='Code Reviewer — automated review with band-aid detection')
    parser.add_argument('file', help='File to review')
    parser.add_argument('--project-root', required=True, help='Project root directory')
    parser.add_argument('--original', dest='original_file', help='Original file for breaking change detection')

    args = parser.parse_args()
    report = review_file(args.file, args.project_root, args.original_file)
    print(json.dumps(asdict(report), indent=2))

    if report.overall_status == 'HALT':
        sys.exit(2)
    elif report.overall_status == 'FAIL':
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
