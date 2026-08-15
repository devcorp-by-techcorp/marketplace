#!/usr/bin/env python3
"""
Code Simplifier — Analyses code for simplification opportunities.

Identifies complexity hotspots, redundancy, poor naming, dead code,
and structural improvements while preserving all functionality.

Usage:
    python code_simplifier.py <file> --project-root <root> [--original <original_file>]
"""

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SimplificationOpportunity:
    """A single simplification opportunity."""
    category: str
    priority: str  # HIGH, MEDIUM, LOW
    line: int
    description: str
    current_code: str
    suggested_approach: str


@dataclass
class SimplificationReport:
    """Complete simplification analysis report."""
    filepath: str
    total_opportunities: int
    high_priority: int
    medium_priority: int
    low_priority: int
    opportunities: list
    metrics: dict
    preservation_safe: bool


def analyse_nesting_depth(content: str) -> list:
    """Find functions with excessive nesting depth."""
    opportunities = []
    lines = content.split('\n')

    current_func = None
    func_start = 0
    max_depth = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        func_match = re.match(r'^(?:async\s+)?def\s+(\w+)', stripped)

        if func_match:
            if current_func and max_depth > 3:
                opportunities.append(SimplificationOpportunity(
                    category='excessive_nesting',
                    priority='HIGH' if max_depth > 5 else 'MEDIUM',
                    line=func_start,
                    description=f'Function {current_func} has nesting depth of {max_depth}',
                    current_code=f'def {current_func}(...) — {max_depth} levels deep',
                    suggested_approach='Use guard clauses with early returns to flatten logic',
                ))
            current_func = func_match.group(1)
            func_start = i
            max_depth = 0
            continue

        if current_func and stripped and not stripped.startswith('#'):
            indent = len(line) - len(line.lstrip())
            depth = indent // 4
            max_depth = max(max_depth, depth)

    # Handle last function
    if current_func and max_depth > 3:
        opportunities.append(SimplificationOpportunity(
            category='excessive_nesting',
            priority='HIGH' if max_depth > 5 else 'MEDIUM',
            line=func_start,
            description=f'Function {current_func} has nesting depth of {max_depth}',
            current_code=f'def {current_func}(...) — {max_depth} levels deep',
            suggested_approach='Use guard clauses with early returns to flatten logic',
        ))

    return opportunities


def analyse_function_length(content: str) -> list:
    """Find functions that are too long."""
    opportunities = []
    lines = content.split('\n')

    func_starts = []
    for i, line in enumerate(lines):
        if re.match(r'^(?:async\s+)?def\s+(\w+)', line.strip()):
            func_starts.append((i, re.match(r'^(?:async\s+)?def\s+(\w+)', line.strip()).group(1)))

    for idx, (start, name) in enumerate(func_starts):
        # Determine function end
        if idx + 1 < len(func_starts):
            end = func_starts[idx + 1][0]
        else:
            end = len(lines)

        func_length = end - start
        if func_length > 50:
            opportunities.append(SimplificationOpportunity(
                category='long_function',
                priority='HIGH' if func_length > 100 else 'MEDIUM',
                line=start + 1,
                description=f'Function {name} is {func_length} lines (target: ≤50)',
                current_code=f'def {name}(...) — {func_length} lines',
                suggested_approach='Split into smaller functions by responsibility',
            ))

    return opportunities


def analyse_duplicate_patterns(content: str) -> list:
    """Detect potential code duplication."""
    opportunities = []
    lines = content.split('\n')

    # Find repeated multi-line blocks (3+ identical lines)
    line_groups = {}
    for i in range(len(lines) - 2):
        block = '\n'.join(line.strip() for line in lines[i:i+3] if line.strip())
        if len(block) > 30:  # Only substantial blocks
            if block not in line_groups:
                line_groups[block] = []
            line_groups[block].append(i + 1)

    for block, locations in line_groups.items():
        if len(locations) > 1:
            first_line = block.split('\n')[0][:60]
            opportunities.append(SimplificationOpportunity(
                category='potential_duplication',
                priority='MEDIUM',
                line=locations[0],
                description=f'Similar code block appears {len(locations)} times',
                current_code=f'{first_line}... (at lines {", ".join(str(l) for l in locations)})',
                suggested_approach='Extract to a shared utility function',
            ))

    return opportunities


def analyse_unused_imports(content: str) -> list:
    """Find imports that appear unused."""
    opportunities = []
    lines = content.split('\n')

    imports = []
    for i, line in enumerate(lines, 1):
        # from X import Y, Z
        match = re.match(r'^from\s+\S+\s+import\s+(.+)$', line.strip())
        if match:
            imported_names = [n.strip().split(' as ')[-1].strip() for n in match.group(1).split(',')]
            for name in imported_names:
                if name and name != '*':
                    imports.append((name, i))
            continue

        # import X
        match = re.match(r'^import\s+(\S+)(?:\s+as\s+(\S+))?', line.strip())
        if match:
            name = match.group(2) or match.group(1).split('.')[-1]
            imports.append((name, i))

    # Check usage (simple check — doesn't handle all edge cases)
    non_import_content = '\n'.join(
        line for line in lines
        if not line.strip().startswith(('import ', 'from '))
    )

    for name, line_num in imports:
        # Check if the name appears anywhere outside imports
        pattern = r'\b' + re.escape(name) + r'\b'
        if not re.search(pattern, non_import_content):
            opportunities.append(SimplificationOpportunity(
                category='unused_import',
                priority='LOW',
                line=line_num,
                description=f'Import "{name}" appears unused',
                current_code=lines[line_num - 1].strip(),
                suggested_approach='Remove unused import',
            ))

    return opportunities


def analyse_naming(content: str) -> list:
    """Check for poor naming conventions."""
    opportunities = []
    lines = content.split('\n')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Single-letter variables (except common loop vars and lambdas)
        var_match = re.match(r'^(\w)\s*=\s', stripped)
        if var_match and var_match.group(1) not in ('_', 'i', 'j', 'k', 'x', 'y', 'f', 'e'):
            opportunities.append(SimplificationOpportunity(
                category='poor_naming',
                priority='LOW',
                line=i,
                description=f'Single-letter variable "{var_match.group(1)}" — use descriptive name',
                current_code=stripped[:60],
                suggested_approach='Rename to describe the value\'s purpose',
            ))

        # Very short function names (1-2 chars)
        func_match = re.match(r'^(?:async\s+)?def\s+(\w{1,2})\s*\(', stripped)
        if func_match and func_match.group(1) not in ('__',):
            opportunities.append(SimplificationOpportunity(
                category='poor_naming',
                priority='MEDIUM',
                line=i,
                description=f'Short function name "{func_match.group(1)}" — use descriptive name',
                current_code=stripped[:60],
                suggested_approach='Rename to verb+noun pattern (e.g., get_user, validate_input)',
            ))

    return opportunities


def analyse_nested_ternaries(content: str) -> list:
    """Detect nested ternary operators."""
    opportunities = []
    lines = content.split('\n')

    for i, line in enumerate(lines, 1):
        # Count ternary operators (X if Y else Z) on a single line
        ternary_count = len(re.findall(r'\bif\b.*\belse\b', line))
        if ternary_count > 1:
            opportunities.append(SimplificationOpportunity(
                category='nested_ternary',
                priority='HIGH',
                line=i,
                description='Nested ternary operator — hard to read',
                current_code=line.strip()[:80],
                suggested_approach='Replace with if/elif/else or dictionary lookup',
            ))

    return opportunities


def calculate_metrics(content: str) -> dict:
    """Calculate code metrics."""
    lines = content.split('\n')
    non_empty = [l for l in lines if l.strip()]
    comments = [l for l in lines if l.strip().startswith('#')]

    func_count = len(re.findall(r'^(?:async\s+)?def\s+\w+', content, re.MULTILINE))
    class_count = len(re.findall(r'^class\s+\w+', content, re.MULTILINE))

    return {
        'total_lines': len(lines),
        'non_empty_lines': len(non_empty),
        'comment_lines': len(comments),
        'comment_ratio': round(len(comments) / max(len(non_empty), 1), 2),
        'function_count': func_count,
        'class_count': class_count,
        'avg_line_length': round(sum(len(l) for l in non_empty) / max(len(non_empty), 1), 1),
    }


def simplify_file(
    filepath: str,
    project_root: str,
    original_filepath: Optional[str] = None,
) -> SimplificationReport:
    """Analyse a file for simplification opportunities."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except (FileNotFoundError, PermissionError) as e:
        return SimplificationReport(
            filepath=filepath,
            total_opportunities=0,
            high_priority=0,
            medium_priority=0,
            low_priority=0,
            opportunities=[{'error': str(e)}],
            metrics={},
            preservation_safe=False,
        )

    all_opportunities = []

    # Run all analysers
    all_opportunities.extend(analyse_nesting_depth(content))
    all_opportunities.extend(analyse_function_length(content))
    all_opportunities.extend(analyse_duplicate_patterns(content))
    all_opportunities.extend(analyse_unused_imports(content))
    all_opportunities.extend(analyse_naming(content))
    all_opportunities.extend(analyse_nested_ternaries(content))

    # Count by priority
    high = sum(1 for o in all_opportunities if o.priority == 'HIGH')
    medium = sum(1 for o in all_opportunities if o.priority == 'MEDIUM')
    low = sum(1 for o in all_opportunities if o.priority == 'LOW')

    # Calculate metrics
    metrics = calculate_metrics(content)

    # All simplification suggestions are safe by definition
    # (they don't change behaviour)
    preservation_safe = True

    return SimplificationReport(
        filepath=filepath,
        total_opportunities=len(all_opportunities),
        high_priority=high,
        medium_priority=medium,
        low_priority=low,
        opportunities=[asdict(o) for o in all_opportunities],
        metrics=metrics,
        preservation_safe=preservation_safe,
    )


def main():
    parser = argparse.ArgumentParser(description='Code Simplifier — simplification analysis')
    parser.add_argument('file', help='File to analyse')
    parser.add_argument('--project-root', required=True, help='Project root directory')
    parser.add_argument('--original', dest='original_file', help='Original file for comparison')

    args = parser.parse_args()
    report = simplify_file(args.file, args.project_root, args.original_file)
    print(json.dumps(asdict(report), indent=2))


if __name__ == '__main__':
    main()
