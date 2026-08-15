#!/usr/bin/env python3
"""
Breaking Change Detector - Identifies changes that break existing functionality.

Usage: python breaking_change_detector.py <original_file> <modified_file>

Returns: JSON report with breaking changes and severity levels
"""

import ast
import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class BreakingChange:
    """Represents a single breaking change."""
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    change_type: str  # removed, signature_changed, renamed, behavior_changed
    symbol: str  # Name of affected function/class
    location: str  # file:line
    before: str  # Original state
    after: str  # New state
    impact: str  # Description of impact
    requires_approval: bool


@dataclass
class BreakingChangeReport:
    """Complete breaking change assessment report."""
    original_file: str
    modified_file: str
    breaking_changes_found: bool
    total_changes: int
    changes_requiring_approval: int
    changes: list
    summary: dict


def extract_public_api(file_path: Path) -> dict:
    """Extract public API surface from a Python file."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            tree = ast.parse(content)
        
        api = {
            'functions': {},
            'classes': {},
            'constants': []
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                args = [(arg.arg, ast.unparse(arg.annotation) if arg.annotation else 'Any') 
                        for arg in node.args.args]
                returns = ast.unparse(node.returns) if node.returns else 'None'
                defaults = [ast.unparse(d) for d in node.args.defaults]
                
                api['functions'][node.name] = {
                    'args': args,
                    'returns': returns,
                    'defaults': defaults,
                    'line': node.lineno,
                    'docstring': ast.get_docstring(node)
                }
            
            elif isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
                methods = {}
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith('_'):
                        args = [(arg.arg, ast.unparse(arg.annotation) if arg.annotation else 'Any')
                                for arg in item.args.args]
                        methods[item.name] = {'args': args, 'line': item.lineno}
                
                api['classes'][node.name] = {
                    'methods': methods,
                    'line': node.lineno,
                    'bases': [ast.unparse(b) for b in node.bases]
                }
            
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        api['constants'].append(target.id)
        
        return api
    except Exception as e:
        return {'functions': {}, 'classes': {}, 'constants': [], 'error': str(e)}


def compare_function_signatures(
    name: str,
    original: dict,
    modified: dict
) -> Optional[BreakingChange]:
    """Compare function signatures for breaking changes."""
    
    # Check if function was removed
    if name not in modified:
        return BreakingChange(
            severity='CRITICAL',
            change_type='removed',
            symbol=name,
            location=f'line {original.get("line", "?")}',
            before=f'def {name}({", ".join(a[0] for a in original["args"])})',
            after='<removed>',
            impact=f'Function "{name}" was removed. All callers will fail.',
            requires_approval=True
        )
    
    orig_args = original['args']
    mod_args = modified[name]['args']
    
    # Check for removed parameters
    orig_arg_names = [a[0] for a in orig_args]
    mod_arg_names = [a[0] for a in mod_args]
    
    removed_args = set(orig_arg_names) - set(mod_arg_names)
    if removed_args:
        return BreakingChange(
            severity='HIGH',
            change_type='signature_changed',
            symbol=name,
            location=f'line {modified[name].get("line", "?")}',
            before=f'def {name}({", ".join(orig_arg_names)})',
            after=f'def {name}({", ".join(mod_arg_names)})',
            impact=f'Parameters removed: {removed_args}. Callers using these params will fail.',
            requires_approval=True
        )
    
    # Check for return type changes
    if original['returns'] != modified[name]['returns']:
        return BreakingChange(
            severity='HIGH',
            change_type='signature_changed',
            symbol=name,
            location=f'line {modified[name].get("line", "?")}',
            before=f'-> {original["returns"]}',
            after=f'-> {modified[name]["returns"]}',
            impact=f'Return type changed. Callers expecting {original["returns"]} may fail.',
            requires_approval=True
        )
    
    return None


def compare_classes(
    name: str,
    original: dict,
    modified: dict
) -> list[BreakingChange]:
    """Compare class definitions for breaking changes."""
    changes = []
    
    # Check if class was removed
    if name not in modified:
        changes.append(BreakingChange(
            severity='CRITICAL',
            change_type='removed',
            symbol=name,
            location=f'line {original.get("line", "?")}',
            before=f'class {name}',
            after='<removed>',
            impact=f'Class "{name}" was removed. All usages will fail.',
            requires_approval=True
        ))
        return changes
    
    # Check for removed methods
    orig_methods = set(original['methods'].keys())
    mod_methods = set(modified[name]['methods'].keys())
    
    removed_methods = orig_methods - mod_methods
    for method in removed_methods:
        changes.append(BreakingChange(
            severity='HIGH',
            change_type='removed',
            symbol=f'{name}.{method}',
            location=f'line {original["methods"][method].get("line", "?")}',
            before=f'{name}.{method}()',
            after='<removed>',
            impact=f'Method "{method}" removed from class "{name}".',
            requires_approval=True
        ))
    
    return changes


def detect_breaking_changes(original_file: str, modified_file: str) -> BreakingChangeReport:
    """Detect all breaking changes between two file versions."""
    orig_path = Path(original_file)
    mod_path = Path(modified_file)
    
    orig_api = extract_public_api(orig_path)
    mod_api = extract_public_api(mod_path)
    
    changes = []
    
    # Compare functions
    for func_name, func_info in orig_api['functions'].items():
        change = compare_function_signatures(func_name, func_info, mod_api['functions'])
        if change:
            changes.append(change)
    
    # Compare classes
    for class_name, class_info in orig_api['classes'].items():
        class_changes = compare_classes(class_name, class_info, mod_api['classes'])
        changes.extend(class_changes)
    
    # Compare constants
    removed_constants = set(orig_api['constants']) - set(mod_api['constants'])
    for const in removed_constants:
        changes.append(BreakingChange(
            severity='MEDIUM',
            change_type='removed',
            symbol=const,
            location='module level',
            before=f'{const} = ...',
            after='<removed>',
            impact=f'Constant "{const}" was removed.',
            requires_approval=True
        ))
    
    # Generate summary
    changes_requiring_approval = len([c for c in changes if c.requires_approval])
    summary = {
        'by_severity': {
            'CRITICAL': len([c for c in changes if c.severity == 'CRITICAL']),
            'HIGH': len([c for c in changes if c.severity == 'HIGH']),
            'MEDIUM': len([c for c in changes if c.severity == 'MEDIUM']),
            'LOW': len([c for c in changes if c.severity == 'LOW'])
        },
        'by_type': {
            'removed': len([c for c in changes if c.change_type == 'removed']),
            'signature_changed': len([c for c in changes if c.change_type == 'signature_changed']),
            'renamed': len([c for c in changes if c.change_type == 'renamed']),
            'behavior_changed': len([c for c in changes if c.change_type == 'behavior_changed'])
        }
    }
    
    return BreakingChangeReport(
        original_file=str(orig_path),
        modified_file=str(mod_path),
        breaking_changes_found=len(changes) > 0,
        total_changes=len(changes),
        changes_requiring_approval=changes_requiring_approval,
        changes=[asdict(c) for c in changes],
        summary=summary
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: python breaking_change_detector.py <original_file> <modified_file>")
        sys.exit(1)
    
    original_file = sys.argv[1]
    modified_file = sys.argv[2]
    
    report = detect_breaking_changes(original_file, modified_file)
    print(json.dumps(asdict(report), indent=2))
    
    # Exit with appropriate code
    if report.changes_requiring_approval > 0:
        sys.exit(1)  # Breaking changes found
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
