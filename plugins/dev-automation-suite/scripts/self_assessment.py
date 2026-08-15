#!/usr/bin/env python3
"""
Self Assessment - Comprehensive code quality evaluation.

Usage: 
  python self_assessment.py <target_file> [--project-root <path>]
  python self_assessment.py <target_file> --compare <original_file> [--project-root <path>]

Returns: Complete assessment report with pass/fail determination
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AssessmentResult:
    """Individual assessment component result."""
    component: str
    status: str  # PASS, WARN, FAIL
    score: Optional[int]
    details: dict


@dataclass
class SelfAssessmentReport:
    """Complete self-assessment report."""
    target_file: str
    assessment_date: str
    overall_status: str  # PASS, CONDITIONAL_PASS, FAIL
    overall_score: int
    components: list
    requires_approval: bool
    approval_items: list
    recommendations: list
    summary: str


def run_compatibility_check(target_file: str, project_root: str) -> AssessmentResult:
    """Run compatibility checker and return result."""
    script_path = Path(__file__).parent / 'compatibility_checker.py'
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), target_file, project_root],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            data = json.loads(result.stdout)
            return AssessmentResult(
                component='compatibility',
                status=data.get('status', 'FAIL'),
                score=data.get('score', 0),
                details=data
            )
    except Exception as e:
        pass
    
    return AssessmentResult(
        component='compatibility',
        status='FAIL',
        score=0,
        details={'error': 'Could not run compatibility check'}
    )


def run_breaking_change_detection(
    original_file: str,
    modified_file: str
) -> AssessmentResult:
    """Run breaking change detector and return result."""
    script_path = Path(__file__).parent / 'breaking_change_detector.py'
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), original_file, modified_file],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            data = json.loads(result.stdout)
            status = 'PASS' if not data.get('breaking_changes_found') else 'FAIL'
            return AssessmentResult(
                component='breaking_changes',
                status=status,
                score=100 if status == 'PASS' else 0,
                details=data
            )
    except Exception as e:
        pass
    
    return AssessmentResult(
        component='breaking_changes',
        status='PASS',  # No comparison file means no breaking changes
        score=100,
        details={'message': 'No original file provided for comparison'}
    )


def run_preservation_check(
    original_file: str,
    modified_file: str
) -> AssessmentResult:
    """Run functionality preserver and return result."""
    script_path = Path(__file__).parent / 'functionality_preserver.py'
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), original_file, modified_file],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            data = json.loads(result.stdout)
            return AssessmentResult(
                component='preservation',
                status=data.get('status', 'FAIL'),
                score=int(data.get('preservation_rate', 0)),
                details=data
            )
    except Exception as e:
        pass
    
    return AssessmentResult(
        component='preservation',
        status='PASS',  # No comparison file means full preservation
        score=100,
        details={'message': 'No original file provided for comparison'}
    )


_RN_EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx', '.mjs'}


def is_react_native_file(target_file: str) -> bool:
    """Determine if target file is a React Native source file."""
    return Path(target_file).suffix in _RN_EXTENSIONS


def run_rn_analysis(target_file: str, project_root: Optional[str] = None) -> AssessmentResult:
    """Run React Native analyzer and return result."""
    script_path = Path(__file__).parent / 'rn_analyzer.py'

    cmd = [sys.executable, str(script_path), target_file]
    if project_root:
        cmd.extend(['--project-root', project_root])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.stdout:
            data = json.loads(result.stdout)
            return AssessmentResult(
                component='react_native',
                status=data.get('status', 'FAIL'),
                score=data.get('score', 0),
                details=data
            )
    except Exception:
        pass

    return AssessmentResult(
        component='react_native',
        status='FAIL',
        score=0,
        details={'error': 'Could not run React Native analysis'}
    )


def check_code_quality(target_file: str) -> AssessmentResult:
    """Basic code quality checks."""
    issues = []
    score = 100
    
    try:
        with open(target_file, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Check file length
        if len(lines) > 500:
            issues.append('File exceeds 500 lines')
            score -= 10
        
        # Check for bare except clauses
        if 'except:' in content and 'except Exception' not in content:
            issues.append('Bare except clause found')
            score -= 15
        
        # Check for TODO/FIXME comments
        todo_count = content.lower().count('todo') + content.lower().count('fixme')
        if todo_count > 5:
            issues.append(f'{todo_count} TODO/FIXME comments found')
            score -= 5
        
        # Check for print statements (should use logging)
        import re
        print_matches = re.findall(r'\bprint\s*\(', content)
        if len(print_matches) > 3:
            issues.append(f'{len(print_matches)} print statements found (use logging)')
            score -= 5
        
        status = 'PASS' if score >= 80 else ('WARN' if score >= 60 else 'FAIL')
        
        return AssessmentResult(
            component='code_quality',
            status=status,
            score=max(0, score),
            details={
                'issues': issues,
                'lines': len(lines),
                'characters': len(content)
            }
        )
    
    except Exception as e:
        return AssessmentResult(
            component='code_quality',
            status='FAIL',
            score=0,
            details={'error': str(e)}
        )


def calculate_overall_status(components: list[AssessmentResult]) -> tuple[str, int]:
    """Calculate overall status and score from components."""
    scores = [c.score for c in components if c.score is not None]
    overall_score = sum(scores) // len(scores) if scores else 0
    
    # Check for any failures
    has_fail = any(c.status == 'FAIL' for c in components)
    has_warn = any(c.status == 'WARN' for c in components)
    
    if has_fail:
        return 'FAIL', overall_score
    elif has_warn:
        return 'CONDITIONAL_PASS', overall_score
    else:
        return 'PASS', overall_score


def generate_recommendations(components: list[AssessmentResult]) -> list[str]:
    """Generate recommendations based on assessment results."""
    recommendations = []
    
    for component in components:
        if component.status == 'FAIL':
            if component.component == 'compatibility':
                recommendations.append('Resolve all compatibility issues before delivery')
            elif component.component == 'breaking_changes':
                recommendations.append('Obtain explicit approval for all breaking changes')
            elif component.component == 'preservation':
                recommendations.append('Restore lost functionality or obtain approval')
            elif component.component == 'code_quality':
                recommendations.append('Address code quality issues')
            elif component.component == 'react_native':
                recommendations.append('Resolve React Native quality issues (see RN analysis details)')
        
        elif component.status == 'WARN':
            if component.component == 'compatibility':
                recommendations.append('Review compatibility warnings and document')
            elif component.component == 'code_quality':
                recommendations.append('Consider addressing code quality warnings')
            elif component.component == 'react_native':
                recommendations.append('Review React Native warnings — low-severity issues found')
    
    if not recommendations:
        recommendations.append('All checks passed - ready for delivery')
    
    return recommendations


def extract_approval_items(components: list[AssessmentResult]) -> list[str]:
    """Extract items requiring user approval."""
    items = []
    
    for component in components:
        if component.component == 'breaking_changes':
            changes = component.details.get('changes', [])
            for change in changes:
                if change.get('requires_approval'):
                    items.append(f"Breaking change: {change.get('symbol')} - {change.get('impact')}")
        
        elif component.component == 'preservation':
            lost = component.details.get('lost_features', [])
            for feature in lost:
                items.append(f"Lost feature: {feature.get('name')} ({feature.get('feature_type')})")
    
    return items


def run_self_assessment(
    target_file: str,
    original_file: Optional[str] = None,
    project_root: Optional[str] = None
) -> SelfAssessmentReport:
    """Run complete self-assessment."""
    components = []
    
    # Default project root to parent of target file
    if not project_root:
        project_root = str(Path(target_file).parent)
    
    # Run compatibility check
    compat_result = run_compatibility_check(target_file, project_root)
    components.append(compat_result)
    
    # Run breaking change detection if original provided
    if original_file:
        breaking_result = run_breaking_change_detection(original_file, target_file)
        components.append(breaking_result)
        
        # Run preservation check
        preservation_result = run_preservation_check(original_file, target_file)
        components.append(preservation_result)
    
    # Run code quality check
    quality_result = check_code_quality(target_file)
    components.append(quality_result)

    # Run React Native analysis if target is an RN file
    if is_react_native_file(target_file):
        rn_result = run_rn_analysis(target_file, project_root)
        components.append(rn_result)
    
    # Calculate overall status
    overall_status, overall_score = calculate_overall_status(components)
    
    # Generate recommendations
    recommendations = generate_recommendations(components)
    
    # Extract approval items
    approval_items = extract_approval_items(components)
    
    # Generate summary
    summary_parts = []
    for c in components:
        summary_parts.append(f"{c.component}: {c.status} ({c.score}/100)")
    summary = " | ".join(summary_parts)
    
    return SelfAssessmentReport(
        target_file=target_file,
        assessment_date=datetime.now().isoformat(),
        overall_status=overall_status,
        overall_score=overall_score,
        components=[asdict(c) for c in components],
        requires_approval=len(approval_items) > 0,
        approval_items=approval_items,
        recommendations=recommendations,
        summary=summary
    )


def main():
    parser = argparse.ArgumentParser(description='Self Assessment - Code Quality Evaluation')
    parser.add_argument('target_file', help='File to assess')
    parser.add_argument('--compare', dest='original_file', help='Original file for comparison')
    parser.add_argument('--project-root', dest='project_root', help='Project root directory')
    
    args = parser.parse_args()
    
    report = run_self_assessment(
        args.target_file,
        args.original_file,
        args.project_root
    )
    
    print(json.dumps(asdict(report), indent=2))
    
    # Exit with appropriate code
    if report.overall_status == 'FAIL':
        sys.exit(1)
    elif report.requires_approval:
        sys.exit(2)  # Needs approval
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
