#!/usr/bin/env python3
"""
Stack Profile — detects a project's stack and emits the matching check profile.

The predecessor suite hard-coded a Python/Flask/MongoEngine assumption into its
phase prompts, which capped its usefulness at one project. This module replaces
that assumption with detection: it reads manifests and config files actually
present in the project and returns the verification items, commands, and
security-sensitive paths that apply.

Profiles compose. A repository holding an Expo app and a Flask API returns both,
because a single flattened checklist would blur what "async error handling"
means in an Express route versus a React Native screen.

Detection is evidence-based and reports its own basis, so a wrong profile is
visible rather than silent. Nothing is written; this is read-only by design.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

MAX_SCAN_DEPTH = 3
SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build',
    '.next', '.expo', 'coverage', '.mypy_cache', '.pytest_cache', 'vendor',
}


@dataclass
class ProfileCheck:
    """One stack-specific verification item added to the base checklist."""

    text: str
    command: str = ''
    security_relevant: bool = False


@dataclass
class StackProfile:
    name: str
    label: str
    evidence: list[str] = field(default_factory=list)
    checks: list[ProfileCheck] = field(default_factory=list)
    security_paths: list[str] = field(default_factory=list)


@dataclass
class DetectionReport:
    project_root: str
    profiles: list[StackProfile] = field(default_factory=list)
    unmatched: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def profile_names(self) -> list[str]:
        return [p.name for p in self.profiles]


# --------------------------------------------------------------------------
# Profile definitions
# --------------------------------------------------------------------------

def _python_flask_checks() -> list[ProfileCheck]:
    return [
        ProfileCheck(
            'All new modules import cleanly with no ImportError/ModuleNotFoundError',
            'python3 -c "import <module>"',
        ),
        ProfileCheck(
            'No provider/client instantiated at import time unless credentials are '
            'guaranteed available — SMTP/SendGrid/SES clients must be lazily instantiated',
        ),
        ProfileCheck(
            'timedelta arithmetic uses .total_seconds(), never .seconds '
            '(which silently truncates past 24h)',
        ),
        ProfileCheck('Type hints present on new/modified function signatures'),
        ProfileCheck(
            'MongoEngine documents store no raw dotted keys (e.g. dict(request.headers)) '
            '— keys sanitised first',
            security_relevant=True,
        ),
        ProfileCheck(
            'Blueprints registered via the existing auto-discovery/registry pattern, '
            'not manually wired',
        ),
        ProfileCheck(
            'User-supplied strings reaching templates are escaped — no raw interpolation (XSS)',
            security_relevant=True,
        ),
    ]


def _typescript_rn_checks() -> list[ProfileCheck]:
    return [
        ProfileCheck('Type check passes with no new errors', 'tsc --noEmit'),
        ProfileCheck(
            'Platform assumptions stated explicitly where the code has no cross-platform path',
        ),
        ProfileCheck('Navigation/route params typed, not `any`'),
        ProfileCheck('Hooks follow rules-of-hooks — no conditional hook calls'),
        ProfileCheck(
            'No version-mismatched API calls against the pinned library versions',
        ),
        ProfileCheck(
            'Secure storage used for tokens and credentials, not AsyncStorage',
            security_relevant=True,
        ),
    ]


def _node_express_checks() -> list[ProfileCheck]:
    return [
        ProfileCheck('Type check / build passes', 'tsc --noEmit'),
        ProfileCheck(
            'New routes match the existing authorisation pattern rather than '
            'inventing new permission checks',
            security_relevant=True,
        ),
        ProfileCheck(
            'SQL migrations are additive/reversible unless a breaking schema change '
            'was explicitly requested and flagged',
            security_relevant=True,
        ),
        ProfileCheck(
            'New endpoints have an OpenAPI entry if the project maintains a contract file',
        ),
        ProfileCheck(
            'Immutable-table triggers are not bypassed by new write paths',
            security_relevant=True,
        ),
        ProfileCheck('No unparameterised SQL — all queries bound', security_relevant=True),
    ]


def _frontend_web_checks() -> list[ProfileCheck]:
    return [
        ProfileCheck('Build succeeds', 'npm run build'),
        ProfileCheck(
            'No user-supplied content written via innerHTML or equivalent',
            security_relevant=True,
        ),
        ProfileCheck('No console errors introduced on the touched routes'),
    ]


def _generic_checks() -> list[ProfileCheck]:
    return [
        ProfileCheck('Build or compile step actually run, not assumed, where supported'),
        ProfileCheck(
            'Existing test suite run if one exists; new code has tests if the '
            'project has a test convention',
        ),
        ProfileCheck('No secrets, keys or tokens committed', security_relevant=True),
    ]


PROFILE_BUILDERS = {
    'python-flask': ('Python / Flask', _python_flask_checks,
                     ['auth', 'login', 'session', 'permission', 'admin']),
    'typescript-rn': ('TypeScript / Expo / React Native', _typescript_rn_checks,
                      ['auth', 'token', 'secure-store', 'permission']),
    'node-express': ('Node / Express / SQL', _node_express_checks,
                     ['auth', 'middleware', 'rbac', 'migration', 'admin']),
    'frontend-web': ('Frontend web', _frontend_web_checks, ['auth', 'login']),
    'generic': ('Generic', _generic_checks, []),
}


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def _iter_files(root: Path, max_depth: int = MAX_SCAN_DEPTH):
    root = root.resolve()
    for path in root.rglob('*'):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if len(rel_parts) > max_depth:
            continue
        if path.is_file():
            yield path


def _read_head(path: Path, limit: int = 20000) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')[:limit]
    except OSError:
        return ''


def detect(project_root: str) -> DetectionReport:
    """Detect stack profiles present in the project, with stated evidence."""
    root = Path(project_root)
    report = DetectionReport(project_root=str(root))

    if not root.is_dir():
        report.notes.append(f'not a directory: {root}')
        report.unmatched = True
        return report

    filenames: dict[str, Path] = {}
    for path in _iter_files(root):
        filenames.setdefault(path.name, path)

    evidence: dict[str, list[str]] = {key: [] for key in PROFILE_BUILDERS}

    # --- Python / Flask
    requirements = filenames.get('requirements.txt')
    pyproject = filenames.get('pyproject.toml')
    for manifest in (requirements, pyproject):
        if not manifest:
            continue
        content = _read_head(manifest).lower()
        if 'flask' in content:
            evidence['python-flask'].append(f'{manifest.name} lists Flask')
        if 'mongoengine' in content or 'pymongo' in content:
            evidence['python-flask'].append(f'{manifest.name} lists a MongoDB driver')
        if 'django' in content or 'fastapi' in content:
            evidence['python-flask'].append(
                f'{manifest.name} lists another Python web framework'
            )
    if filenames.get('app.py') or filenames.get('wsgi.py'):
        evidence['python-flask'].append('Python web entry point present')

    # --- Node ecosystem
    package_json = filenames.get('package.json')
    pkg_data: dict = {}
    if package_json:
        raw = _read_head(package_json)
        try:
            pkg_data = json.loads(raw)
        except json.JSONDecodeError:
            report.notes.append('package.json present but could not be parsed')
        deps = {}
        for key in ('dependencies', 'devDependencies', 'peerDependencies'):
            value = pkg_data.get(key)
            if isinstance(value, dict):
                deps.update(value)
        dep_names = {name.lower() for name in deps}

        if {'expo', 'react-native'} & dep_names:
            evidence['typescript-rn'].append('package.json lists expo or react-native')
        if 'express' in dep_names or 'fastify' in dep_names or 'koa' in dep_names:
            evidence['node-express'].append('package.json lists a Node server framework')
        if {'pg', 'postgres', 'knex', 'prisma', 'typeorm', 'sequelize'} & dep_names:
            evidence['node-express'].append('package.json lists a SQL client or ORM')
        if {'react', 'vue', 'svelte', 'next'} & dep_names and not (
            {'expo', 'react-native'} & dep_names
        ):
            evidence['frontend-web'].append('package.json lists a web UI framework')

    if filenames.get('app.json') or filenames.get('eas.json'):
        evidence['typescript-rn'].append('Expo config present (app.json / eas.json)')
    if filenames.get('tsconfig.json'):
        for key in ('typescript-rn', 'node-express', 'frontend-web'):
            if evidence[key]:
                evidence[key].append('tsconfig.json present')

    for name, found in evidence.items():
        if not found:
            continue
        label, builder, sec_paths = PROFILE_BUILDERS[name]
        report.profiles.append(
            StackProfile(
                name=name,
                label=label,
                evidence=sorted(set(found)),
                checks=builder(),
                security_paths=sec_paths,
            )
        )

    if not report.profiles:
        report.unmatched = True
        report.notes.append(
            'no stack signature matched; falling back to the generic profile. '
            'Detection reads manifests up to depth '
            f'{MAX_SCAN_DEPTH} — a monorepo may need a subdirectory as project root.'
        )

    label, builder, sec_paths = PROFILE_BUILDERS['generic']
    report.profiles.append(
        StackProfile(
            name='generic',
            label=label,
            evidence=['always applied'],
            checks=builder(),
            security_paths=sec_paths,
        )
    )
    return report


def render_checklist(report: DetectionReport, start_index: int = 8) -> str:
    """Render detected checks as numbered items appended to the base checklist."""
    lines: list[str] = []
    index = start_index
    for profile in report.profiles:
        lines.append(f'<!-- {profile.label} -->')
        for check in profile.checks:
            suffix = f' (`{check.command}`)' if check.command else ''
            marker = ' **[security]**' if check.security_relevant else ''
            lines.append(f'{index}. {check.text}{suffix}{marker}')
            index += 1
        lines.append('')
    return '\n'.join(lines).rstrip()


def render_text(report: DetectionReport) -> str:
    lines = ['Stack Profile Detection', '=' * 60, f'Project: {report.project_root}', '']
    for profile in report.profiles:
        lines.append(f'[{profile.name}] {profile.label}')
        for item in profile.evidence:
            lines.append(f'    evidence: {item}')
        lines.append(f'    checks: {len(profile.checks)}')
        if profile.security_paths:
            lines.append(f'    security terms: {", ".join(profile.security_paths)}')
        lines.append('')
    for note in report.notes:
        lines.append(f'note: {note}')
    lines.append('')
    lines.append('Checklist additions:')
    lines.append(render_checklist(report))
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Detect project stack and emit the matching verification profile.',
    )
    parser.add_argument('project_root', help='Project root directory')
    parser.add_argument('--json', action='store_true', help='Emit JSON')
    parser.add_argument(
        '--checklist',
        action='store_true',
        help='Emit only the numbered checklist additions',
    )
    parser.add_argument(
        '--start-index',
        type=int,
        default=8,
        help='First number for checklist additions (base checklist ends at 7)',
    )
    args = parser.parse_args()

    report = detect(args.project_root)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    elif args.checklist:
        print(render_checklist(report, args.start_index))
    else:
        print(render_text(report))

    sys.exit(0)


if __name__ == '__main__':
    from _cli import guard_broken_pipe
    guard_broken_pipe(main)
