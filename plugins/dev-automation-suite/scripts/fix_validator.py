#!/usr/bin/env python3
"""
Fix Validator — Validates that code changes are permanent fixes, not band-aids.

Compares original and fixed files to ensure:
1. The fix addresses root cause, not symptoms
2. No band-aid patterns were introduced
3. No functionality was lost
4. No breaking changes were made

Usage:
    python fix_validator.py <original> <fixed> --project-root <root>
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Optional


# Patterns that indicate a band-aid rather than a proper fix
BAND_AID_DIFF_PATTERNS = [
    {
        'pattern': r'^\+.*except\s*:\s*pass',
        'name': 'added_except_pass',
        'description': 'Added bare except with pass — swallows errors instead of fixing them',
    },
    {
        'pattern': r'^\+.*except\s+\w+.*:\s*pass',
        'name': 'added_typed_except_pass',
        'description': 'Added typed except with pass — ignores errors instead of handling them',
    },
    {
        'pattern': r'^\+.*except.*:\s*return\s+None',
        'name': 'added_except_return_none',
        'description': 'Added exception handler that returns None — masks failure',
    },
    {
        'pattern': r'^\+.*#\s*noqa',
        'name': 'added_noqa',
        'description': 'Added noqa suppression — hides issue instead of fixing it',
    },
    {
        'pattern': r'^\+.*#\s*type:\s*ignore',
        'name': 'added_type_ignore',
        'description': 'Added type: ignore — suppresses type error instead of fixing it',
    },
    {
        'pattern': r'^\+.*#\s*pylint:\s*disable',
        'name': 'added_pylint_disable',
        'description': 'Added pylint disable — suppresses lint warning instead of fixing it',
    },
    {
        'pattern': r'^\+.*(?:HACK|WORKAROUND|BAND.?AID|TEMP(?:ORARY)?)',
        'name': 'added_hack_comment',
        'description': 'Added comment acknowledging a workaround or hack',
    },
    {
        'pattern': r'^\+.*timeout\s*=\s*9{3,}',
        'name': 'added_absurd_timeout',
        'description': 'Added absurdly high timeout — avoids timeout instead of fixing cause',
    },
    {
        'pattern': r'^\+\s*#.*(?:disabled|commented out|skip|bypass)',
        'name': 'added_skip_comment',
        'description': 'Comment suggests code was disabled as a fix',
    },
]

# Patterns indicating code was disabled rather than fixed
CODE_DISABLE_PATTERNS = [
    {
        'pattern': r'^-\s*(\S.+)$',  # Removed line
        'check_commented': r'^\+\s*#\s*{content}',  # Same line now commented
        'name': 'commented_out_code',
        'description': 'Code was commented out instead of fixed or properly removed',
    },
]


@dataclass
class FixValidationResult:
    """Result of fix validation."""
    original_file: str
    fixed_file: str
    is_valid_fix: bool
    band_aids_found: int
    band_aid_details: list
    functionality_preserved: bool
    lost_symbols: list
    added_symbols: list
    changed_symbols: list
    diff_stats: dict
    verdict: str


def extract_symbols(content: str) -> dict:
    """Extract all public symbols from code."""
    symbols = {
        'functions': {},
        'classes': {},
        'constants': [],
    }

    for match in re.finditer(r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)', content, re.MULTILINE):
        name = match.group(1)
        params = match.group(2).strip()
        symbols['functions'][name] = params

    for match in re.finditer(r'^class\s+(\w+)\s*(?:\((.*?)\))?:', content, re.MULTILINE):
        name = match.group(1)
        bases = match.group(2) or ''
        symbols['classes'][name] = bases.strip()

    for match in re.finditer(r'^([A-Z][A-Z0-9_]+)\s*=', content, re.MULTILINE):
        symbols['constants'].append(match.group(1))

    return symbols


def generate_diff(original: str, fixed: str) -> list:
    """Generate unified diff between original and fixed content."""
    orig_lines = original.split('\n')
    fixed_lines = fixed.split('\n')
    return list(unified_diff(orig_lines, fixed_lines, lineterm=''))


def check_band_aid_in_diff(diff_lines: list) -> list:
    """Check diff for band-aid patterns in added lines."""
    findings = []

    for i, line in enumerate(diff_lines):
        for pattern_def in BAND_AID_DIFF_PATTERNS:
            if re.search(pattern_def['pattern'], line, re.IGNORECASE):
                findings.append({
                    'pattern': pattern_def['name'],
                    'description': pattern_def['description'],
                    'diff_line': i + 1,
                    'content': line.strip()[:100],
                })

    return findings


def check_commented_out_code(diff_lines: list) -> list:
    """Detect code that was commented out instead of fixed."""
    findings = []
    removed_lines = []
    added_lines = []

    for line in diff_lines:
        if line.startswith('-') and not line.startswith('---'):
            removed_lines.append(line[1:].strip())
        elif line.startswith('+') and not line.startswith('+++'):
            added_lines.append(line[1:].strip())

    for removed in removed_lines:
        if not removed:
            continue
        # Check if the same content appears as a comment in added lines
        for added in added_lines:
            if added.startswith('#') and removed in added:
                findings.append({
                    'pattern': 'commented_out_code',
                    'description': 'Code was commented out instead of being fixed or properly removed',
                    'removed': removed[:80],
                    'added_as_comment': added[:80],
                })
                break

    return findings


def check_functionality_preservation(original_symbols: dict, fixed_symbols: dict) -> dict:
    """Check that no public functionality was lost."""
    lost = []
    added = []
    changed = []

    # Check functions
    for name, params in original_symbols['functions'].items():
        if name not in fixed_symbols['functions']:
            lost.append({'type': 'function', 'name': name, 'original_params': params})
        elif fixed_symbols['functions'][name] != params:
            changed.append({
                'type': 'function',
                'name': name,
                'original_params': params,
                'new_params': fixed_symbols['functions'][name],
            })

    for name in fixed_symbols['functions']:
        if name not in original_symbols['functions']:
            added.append({'type': 'function', 'name': name})

    # Check classes
    for name in original_symbols['classes']:
        if name not in fixed_symbols['classes']:
            lost.append({'type': 'class', 'name': name})

    for name in fixed_symbols['classes']:
        if name not in original_symbols['classes']:
            added.append({'type': 'class', 'name': name})

    # Check constants
    for name in original_symbols['constants']:
        if name not in fixed_symbols['constants']:
            lost.append({'type': 'constant', 'name': name})

    return {
        'preserved': len(lost) == 0,
        'lost': lost,
        'added': added,
        'changed': changed,
    }


def calculate_diff_stats(diff_lines: list) -> dict:
    """Calculate statistics about the diff."""
    added = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
    removed = sum(1 for l in diff_lines if l.startswith('-') and not l.startswith('---'))

    return {
        'lines_added': added,
        'lines_removed': removed,
        'total_changes': added + removed,
        'net_change': added - removed,
    }


def validate_fix(
    original_filepath: str,
    fixed_filepath: str,
    project_root: str,
) -> FixValidationResult:
    """Validate that a fix is permanent and not a band-aid."""
    try:
        with open(original_filepath, 'r') as f:
            original_content = f.read()
        with open(fixed_filepath, 'r') as f:
            fixed_content = f.read()
    except (FileNotFoundError, PermissionError) as e:
        return FixValidationResult(
            original_file=original_filepath,
            fixed_file=fixed_filepath,
            is_valid_fix=False,
            band_aids_found=0,
            band_aid_details=[{'error': str(e)}],
            functionality_preserved=False,
            lost_symbols=[],
            added_symbols=[],
            changed_symbols=[],
            diff_stats={},
            verdict=f'ERROR: {e}',
        )

    # Generate diff
    diff_lines = generate_diff(original_content, fixed_content)

    # Check for band-aid patterns in the diff
    band_aid_findings = check_band_aid_in_diff(diff_lines)
    commented_out = check_commented_out_code(diff_lines)
    all_band_aids = band_aid_findings + commented_out

    # Check functionality preservation
    original_symbols = extract_symbols(original_content)
    fixed_symbols = extract_symbols(fixed_content)
    preservation = check_functionality_preservation(original_symbols, fixed_symbols)

    # Calculate diff stats
    diff_stats = calculate_diff_stats(diff_lines)

    # Determine verdict
    is_valid = len(all_band_aids) == 0 and preservation['preserved']

    if not is_valid:
        reasons = []
        if all_band_aids:
            reasons.append(f'{len(all_band_aids)} band-aid pattern(s) detected')
        if not preservation['preserved']:
            lost_names = [s['name'] for s in preservation['lost']]
            reasons.append(f'Lost symbols: {", ".join(lost_names)}')
        verdict = f'REJECTED: {"; ".join(reasons)}'
    else:
        verdict = 'APPROVED: Fix is permanent and preserves all functionality'

    return FixValidationResult(
        original_file=original_filepath,
        fixed_file=fixed_filepath,
        is_valid_fix=is_valid,
        band_aids_found=len(all_band_aids),
        band_aid_details=all_band_aids,
        functionality_preserved=preservation['preserved'],
        lost_symbols=preservation['lost'],
        added_symbols=preservation['added'],
        changed_symbols=preservation['changed'],
        diff_stats=diff_stats,
        verdict=verdict,
    )


def main():
    parser = argparse.ArgumentParser(description='Fix Validator — validates fixes are permanent')
    parser.add_argument('original', help='Original file before fix')
    parser.add_argument('fixed', help='Fixed file')
    parser.add_argument('--project-root', required=True, help='Project root directory')

    args = parser.parse_args()
    result = validate_fix(args.original, args.fixed, args.project_root)
    print(json.dumps(asdict(result), indent=2))

    sys.exit(0 if result.is_valid_fix else 1)


if __name__ == '__main__':
    main()
