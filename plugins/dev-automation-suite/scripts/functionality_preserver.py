#!/usr/bin/env python3
"""
Functionality Preserver - Ensures all original features remain intact.

Usage: python functionality_preserver.py <original_file> <modified_file>

Returns: JSON report with preserved/lost functionality mapping
"""

import ast
import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Feature:
    """Represents a single feature/functionality."""
    name: str
    feature_type: str  # function, class, method, constant
    location: str  # file:line
    signature: str  # Full signature
    docstring: Optional[str]


@dataclass
class FeatureStatus:
    """Status of a feature after modification."""
    feature: Feature
    status: str  # preserved, modified, lost
    modification_details: Optional[str]


@dataclass
class PreservationReport:
    """Complete functionality preservation report."""
    original_file: str
    modified_file: str
    original_feature_count: int
    preserved_count: int
    modified_count: int
    lost_count: int
    preservation_rate: float
    status: str  # PASS, WARN, FAIL
    features: list
    lost_features: list
    summary: dict


def extract_features(file_path: Path) -> list[Feature]:
    """Extract all features from a Python file."""
    features = []
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = [arg.arg for arg in node.args.args]
                signature = f"def {node.name}({', '.join(args)})"
                if node.returns:
                    signature += f" -> {ast.unparse(node.returns)}"
                
                features.append(Feature(
                    name=node.name,
                    feature_type='function',
                    location=f'line {node.lineno}',
                    signature=signature,
                    docstring=ast.get_docstring(node)
                ))
            
            elif isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                signature = f"class {node.name}"
                if bases:
                    signature += f"({', '.join(bases)})"
                
                features.append(Feature(
                    name=node.name,
                    feature_type='class',
                    location=f'line {node.lineno}',
                    signature=signature,
                    docstring=ast.get_docstring(node)
                ))
                
                # Extract methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_args = [arg.arg for arg in item.args.args]
                        method_sig = f"{node.name}.{item.name}({', '.join(method_args)})"
                        
                        features.append(Feature(
                            name=f"{node.name}.{item.name}",
                            feature_type='method',
                            location=f'line {item.lineno}',
                            signature=method_sig,
                            docstring=ast.get_docstring(item)
                        ))
            
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        features.append(Feature(
                            name=target.id,
                            feature_type='constant' if target.id.isupper() else 'variable',
                            location=f'line {node.lineno}',
                            signature=f"{target.id} = ...",
                            docstring=None
                        ))
    
    except Exception as e:
        pass
    
    return features


def compare_features(
    original_features: list[Feature],
    modified_features: list[Feature]
) -> list[FeatureStatus]:
    """Compare features between original and modified versions."""
    results = []
    
    # Create lookup for modified features
    mod_by_name = {f.name: f for f in modified_features}
    
    for orig_feature in original_features:
        if orig_feature.name in mod_by_name:
            mod_feature = mod_by_name[orig_feature.name]
            
            # Check if signature changed
            if orig_feature.signature != mod_feature.signature:
                results.append(FeatureStatus(
                    feature=orig_feature,
                    status='modified',
                    modification_details=f'Signature changed from "{orig_feature.signature}" to "{mod_feature.signature}"'
                ))
            else:
                results.append(FeatureStatus(
                    feature=orig_feature,
                    status='preserved',
                    modification_details=None
                ))
        else:
            results.append(FeatureStatus(
                feature=orig_feature,
                status='lost',
                modification_details=f'Feature "{orig_feature.name}" not found in modified file'
            ))
    
    return results


def check_preservation(original_file: str, modified_file: str) -> PreservationReport:
    """Run full preservation check."""
    orig_path = Path(original_file)
    mod_path = Path(modified_file)
    
    orig_features = extract_features(orig_path)
    mod_features = extract_features(mod_path)
    
    feature_status = compare_features(orig_features, mod_features)
    
    # Count statuses
    preserved = len([f for f in feature_status if f.status == 'preserved'])
    modified = len([f for f in feature_status if f.status == 'modified'])
    lost = len([f for f in feature_status if f.status == 'lost'])
    total = len(orig_features)
    
    # Calculate preservation rate
    preservation_rate = (preserved / total * 100) if total > 0 else 100.0
    
    # Determine status
    if lost > 0:
        status = 'FAIL'
    elif modified > 0:
        status = 'WARN'
    else:
        status = 'PASS'
    
    # Extract lost features for easy reference
    lost_features = [
        asdict(f.feature) for f in feature_status if f.status == 'lost'
    ]
    
    # Generate summary
    summary = {
        'by_type': {
            'functions': len([f for f in orig_features if f.feature_type == 'function']),
            'classes': len([f for f in orig_features if f.feature_type == 'class']),
            'methods': len([f for f in orig_features if f.feature_type == 'method']),
            'constants': len([f for f in orig_features if f.feature_type == 'constant'])
        },
        'preservation_by_type': {
            'functions': len([f for f in feature_status 
                           if f.feature.feature_type == 'function' and f.status == 'preserved']),
            'classes': len([f for f in feature_status 
                         if f.feature.feature_type == 'class' and f.status == 'preserved']),
            'methods': len([f for f in feature_status 
                         if f.feature.feature_type == 'method' and f.status == 'preserved']),
            'constants': len([f for f in feature_status 
                           if f.feature.feature_type == 'constant' and f.status == 'preserved'])
        }
    }
    
    return PreservationReport(
        original_file=str(orig_path),
        modified_file=str(mod_path),
        original_feature_count=total,
        preserved_count=preserved,
        modified_count=modified,
        lost_count=lost,
        preservation_rate=round(preservation_rate, 2),
        status=status,
        features=[{
            'feature': asdict(f.feature),
            'status': f.status,
            'modification_details': f.modification_details
        } for f in feature_status],
        lost_features=lost_features,
        summary=summary
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: python functionality_preserver.py <original_file> <modified_file>")
        sys.exit(1)
    
    original_file = sys.argv[1]
    modified_file = sys.argv[2]
    
    report = check_preservation(original_file, modified_file)
    print(json.dumps(asdict(report), indent=2))
    
    # Exit with appropriate code
    if report.status == 'FAIL':
        sys.exit(1)
    elif report.status == 'WARN':
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
