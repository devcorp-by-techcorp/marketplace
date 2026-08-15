#!/usr/bin/env python3
"""
Compatibility Checker - Validates code compatibility with existing project files.

Usage: python compatibility_checker.py <target_file> <project_root>

Returns: JSON report with compatibility score and issues
"""

import ast
import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class CompatibilityIssue:
    """Represents a single compatibility issue."""
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    category: str  # import, signature, interface, integration
    location: str  # file:line
    description: str
    recommendation: str


@dataclass 
class CompatibilityReport:
    """Complete compatibility assessment report."""
    target_file: str
    project_root: str
    score: int  # 0-100
    status: str  # PASS, WARN, FAIL
    issues: list
    summary: dict


def extract_imports(file_path: Path) -> list[str]:
    """Extract all import statements from a Python file."""
    try:
        with open(file_path, 'r') as f:
            tree = ast.parse(f.read())
        
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports
    except Exception as e:
        return []


def extract_function_signatures(file_path: Path) -> dict:
    """Extract all function signatures from a Python file."""
    try:
        with open(file_path, 'r') as f:
            tree = ast.parse(f.read())
        
        signatures = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = [arg.arg for arg in node.args.args]
                signatures[node.name] = {
                    'args': args,
                    'line': node.lineno,
                    'is_public': not node.name.startswith('_')
                }
        return signatures
    except Exception as e:
        return {}


def find_project_files(project_root: Path, extension: str = '.py') -> list[Path]:
    """Find all files with given extension in project."""
    return list(project_root.rglob(f'*{extension}'))


def check_import_compatibility(
    target_imports: list[str],
    project_files: list[Path],
    project_root: Path
) -> list[CompatibilityIssue]:
    """Check if target imports are compatible with project."""
    issues = []
    
    # Get all modules available in project
    project_modules = set()
    for pf in project_files:
        relative = pf.relative_to(project_root)
        module_name = str(relative.with_suffix('')).replace('/', '.')
        project_modules.add(module_name)
    
    # Check each import
    for imp in target_imports:
        # Skip standard library and third-party imports
        if imp.startswith(('os', 'sys', 'json', 'typing', 'dataclasses')):
            continue
        
        # Check if it's a project import that exists
        if any(imp.startswith(pm) for pm in project_modules):
            if not any(imp == pm or imp.startswith(pm + '.') for pm in project_modules):
                issues.append(CompatibilityIssue(
                    severity='HIGH',
                    category='import',
                    location=f'import {imp}',
                    description=f'Import "{imp}" not found in project',
                    recommendation='Verify the import path exists or create the module'
                ))
    
    return issues


def calculate_score(issues: list[CompatibilityIssue]) -> int:
    """Calculate compatibility score based on issues."""
    score = 100
    
    severity_penalties = {
        'CRITICAL': 30,
        'HIGH': 15,
        'MEDIUM': 5,
        'LOW': 2
    }
    
    for issue in issues:
        score -= severity_penalties.get(issue.severity, 5)
    
    return max(0, score)


def determine_status(score: int) -> str:
    """Determine pass/fail status based on score."""
    if score >= 95:
        return 'PASS'
    elif score >= 80:
        return 'WARN'
    else:
        return 'FAIL'


def check_compatibility(target_file: str, project_root: str) -> CompatibilityReport:
    """Run full compatibility check."""
    target_path = Path(target_file)
    root_path = Path(project_root)
    
    issues = []
    
    # Extract target file information
    target_imports = extract_imports(target_path)
    target_signatures = extract_function_signatures(target_path)
    
    # Find project files
    project_files = find_project_files(root_path)
    
    # Check import compatibility
    import_issues = check_import_compatibility(target_imports, project_files, root_path)
    issues.extend(import_issues)
    
    # Calculate score and status
    score = calculate_score(issues)
    status = determine_status(score)
    
    # Generate summary
    summary = {
        'total_issues': len(issues),
        'by_severity': {
            'CRITICAL': len([i for i in issues if i.severity == 'CRITICAL']),
            'HIGH': len([i for i in issues if i.severity == 'HIGH']),
            'MEDIUM': len([i for i in issues if i.severity == 'MEDIUM']),
            'LOW': len([i for i in issues if i.severity == 'LOW'])
        },
        'imports_checked': len(target_imports),
        'functions_found': len(target_signatures)
    }
    
    return CompatibilityReport(
        target_file=str(target_path),
        project_root=str(root_path),
        score=score,
        status=status,
        issues=[asdict(i) for i in issues],
        summary=summary
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: python compatibility_checker.py <target_file> <project_root>")
        sys.exit(1)
    
    target_file = sys.argv[1]
    project_root = sys.argv[2]
    
    report = check_compatibility(target_file, project_root)
    print(json.dumps(asdict(report), indent=2))
    
    # Exit with appropriate code
    if report.status == 'FAIL':
        sys.exit(1)
    elif report.status == 'WARN':
        sys.exit(0)  # Warning but proceed
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
