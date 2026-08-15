#!/usr/bin/env python3
"""
Ground File — project assumption tracking with an enforced audit trail.

The verification gate checks what an agent claims about *code*. This module
covers the other half: what the agent assumes about the *project*. Work built on
an unvalidated premise fails just as hard as work built on a hallucinated API,
and neither the code review nor the compatibility check can see it, because
nothing in the diff is wrong — the premise was.

Two independent axes, deliberately not collapsed:

  * **type** — how the assumption was derived: stated, inferred, assumed,
    uncertain. Immutable once set. This is the audit trail; rewriting how you
    came to believe something destroys the record that makes the belief
    reviewable.
  * **tier** — how confident the project is in it now: ESTABLISHED, WORKING,
    OPEN. Freely adjustable as evidence arrives.

This mirrors the severity/confidence split in the evidence model, and for the
same reason: conflating derivation with confidence produces both false alarm and
false assurance.

Type immutability is enforced in code, not by convention. There is no CLI path
that changes a type. ``promote`` and ``demote`` move tiers only.

Standard library only. Read-only unless a mutating subcommand is given.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

STATED = 'stated'
INFERRED = 'inferred'
ASSUMED = 'assumed'
UNCERTAIN = 'uncertain'
TYPES = (STATED, INFERRED, ASSUMED, UNCERTAIN)

ESTABLISHED = 'ESTABLISHED'
WORKING = 'WORKING'
OPEN = 'OPEN'
TIERS = (ESTABLISHED, WORKING, OPEN)
TIER_ORDER = {OPEN: 0, WORKING: 1, ESTABLISHED: 2}

#: How an assumption's derivation maps onto the verification gate's status
#: vocabulary. Both describe how a claim was arrived at, so an agent that can
#: report one can report the other without a second judgment call.
TYPE_TO_STATUS = {
    STATED: 'OBSERVED',
    INFERRED: 'INFERRED',
    ASSUMED: 'CLAIMED',
    UNCERTAIN: 'UNVERIFIED',
}

#: Default staleness horizon. An ESTABLISHED assumption validated a year ago is
#: not established, it is stale, and the distinction matters most on the
#: assumptions nobody has thought about recently.
DEFAULT_MAX_AGE_DAYS = 90

DEFAULT_ROOT = Path.home() / '.claude' / 'common-ground'

# High-impact subject matter. An OPEN assumption here blocks rather than warns:
# architecture and security premises are expensive to unwind after the fact.
HIGH_IMPACT_KEYWORDS = (
    'auth', 'authn', 'authz', 'authentication', 'authorisation', 'authorization',
    'permission', 'rbac', 'role', 'tenant', 'isolation', 'security', 'credential',
    'secret', 'token', 'encryption', 'pii', 'sensitive', 'regulated', 'compliance',
    'architecture', 'database', 'schema', 'migration', 'data model', 'persistence',
    'payment', 'billing', 'financial', 'transaction',
    'ssr', 'rendering', 'deployment', 'infrastructure', 'breaking change',
)


class GroundError(ValueError):
    """Raised on an invalid mutation, such as an attempt to change a type."""


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class Assumption:
    id: str
    title: str
    assumption: str
    type: str
    tier: str
    evidence: str = ''
    created: str = ''
    last_validated: str = ''

    def __post_init__(self):
        if self.type not in TYPES:
            raise GroundError(f'unknown type {self.type!r}; expected one of {TYPES}')
        if self.tier not in TIERS:
            raise GroundError(f'unknown tier {self.tier!r}; expected one of {TIERS}')

    @property
    def high_impact(self) -> bool:
        haystack = f'{self.title} {self.assumption}'.lower()
        return any(keyword in haystack for keyword in HIGH_IMPACT_KEYWORDS)

    @property
    def gate_status(self) -> str:
        """The evidence-model status this assumption's derivation corresponds to."""
        return TYPE_TO_STATUS[self.type]

    def age_days(self, now: Optional[datetime] = None) -> Optional[int]:
        stamp = self.last_validated or self.created
        if not stamp:
            return None
        try:
            when = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        except ValueError:
            return None
        now = now or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, (now - when).days)

    def is_stale(self, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
        age = self.age_days()
        return age is not None and age > max_age_days


@dataclass
class GroundFile:
    project_id: str
    updated: str = ''
    assumptions: list[Assumption] = field(default_factory=list)

    def by_tier(self, tier: str) -> list[Assumption]:
        return [a for a in self.assumptions if a.tier == tier]

    def get(self, assumption_id: str) -> Optional[Assumption]:
        for item in self.assumptions:
            if item.id == assumption_id:
                return item
        return None

    def next_id(self) -> str:
        used = set()
        for item in self.assumptions:
            match = re.fullmatch(r'A(\d+)', item.id)
            if match:
                used.add(int(match.group(1)))
        return f'A{(max(used) + 1) if used else 1}'


# --------------------------------------------------------------------------
# Project identity
# --------------------------------------------------------------------------

def project_id(project_root: str = '.') -> str:
    """Identify the project by git remote, falling back to its path.

    A remote is preferred because it is stable across clones and machines; a
    path-derived id is local to one checkout and is prefixed ``local/`` so that
    is visible rather than implied.
    """
    try:
        result = subprocess.run(
            ['git', '-C', str(project_root), 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, timeout=10,
        )
        url = result.stdout.strip()
        if result.returncode == 0 and url:
            url = re.sub(r'^https?://', '', url)
            url = re.sub(r'^git@', '', url)
            url = re.sub(r'\.git$', '', url)
            url = url.replace(':', '/', 1)
            return url.strip('/')
    except (OSError, subprocess.SubprocessError):
        pass

    resolved = Path(project_root).resolve()
    return 'local/' + str(resolved).lstrip('/\\').replace('/', '-').replace('\\', '-')


def ground_dir(pid: str, root: Optional[Path] = None) -> Path:
    return (root or DEFAULT_ROOT) / pid


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load(pid: str, root: Optional[Path] = None) -> GroundFile:
    """Load the machine-readable index. Absent file yields an empty ground file."""
    index_path = ground_dir(pid, root) / 'ground.index.json'
    if not index_path.is_file():
        return GroundFile(project_id=pid)
    try:
        data = json.loads(index_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise GroundError(f'ground index unreadable at {index_path}: {exc}') from None

    assumptions = []
    for record in data.get('assumptions', []):
        try:
            assumptions.append(Assumption(**{
                k: record.get(k, '') for k in
                ('id', 'title', 'assumption', 'type', 'tier',
                 'evidence', 'created', 'last_validated')
            }))
        except (GroundError, TypeError) as exc:
            raise GroundError(f'invalid assumption {record.get("id")!r}: {exc}') from None

    return GroundFile(
        project_id=data.get('project_id', pid),
        updated=data.get('updated', ''),
        assumptions=assumptions,
    )


def save(ground: GroundFile, root: Optional[Path] = None) -> tuple[Path, Path]:
    """Write both representations. Returns (markdown_path, index_path).

    Both are written together and always: a machine-readable index that has
    drifted from the human-readable file is worse than having only one, because
    each reader trusts a different version.
    """
    directory = ground_dir(ground.project_id, root)
    directory.mkdir(parents=True, exist_ok=True)
    ground.updated = _now()

    index_path = directory / 'ground.index.json'
    index_path.write_text(
        json.dumps(
            {
                'project_id': ground.project_id,
                'updated': ground.updated,
                'assumptions': [asdict(a) for a in ground.assumptions],
            },
            indent=2,
        ),
        encoding='utf-8',
    )

    md_path = directory / 'COMMON-GROUND.md'
    md_path.write_text(render_markdown(ground), encoding='utf-8')
    return md_path, index_path


def render_markdown(ground: GroundFile) -> str:
    lines = [
        '# Common Ground',
        '',
        f'**Project:** {ground.project_id}',
        f'**Last updated:** {ground.updated or _now()}',
        '',
        'Assumptions this project is operating on, by confidence tier. Types record',
        'how each was derived and never change; tiers record current confidence and',
        'move as evidence arrives.',
        '',
    ]
    for tier in (ESTABLISHED, WORKING, OPEN):
        items = ground.by_tier(tier)
        lines.append(f'## {tier} ({len(items)})')
        lines.append('')
        if not items:
            lines.append('_None._')
            lines.append('')
            continue
        for item in items:
            flags = []
            if item.high_impact:
                flags.append('high-impact')
            if item.is_stale():
                flags.append(f'stale ({item.age_days()}d)')
            suffix = f' — _{", ".join(flags)}_' if flags else ''
            lines.append(f'- **{item.id} · {item.title}** [{item.type}]{suffix}')
            lines.append(f'  {item.assumption}')
            if item.evidence:
                lines.append(f'  _Evidence:_ {item.evidence}')
        lines.append('')

    open_items = ground.by_tier(OPEN)
    if open_items:
        lines.append('---')
        lines.append('')
        lines.append('**OPEN assumptions require validation before work depends on them.**')
        lines.append('An OPEN premise on a high-impact subject blocks the verification gate.')
        lines.append('')
    return '\n'.join(lines)


# --------------------------------------------------------------------------
# Mutation — tier only, never type
# --------------------------------------------------------------------------

def add(
    ground: GroundFile,
    title: str,
    assumption: str,
    a_type: str,
    tier: Optional[str] = None,
    evidence: str = '',
) -> Assumption:
    """Add an assumption. Tier defaults by type and impact, not to a fixed value.

    High-impact assumptions start OPEN unless they were explicitly stated,
    because the cost of being wrong about architecture or security is paid much
    later than the cost of asking now.
    """
    if a_type not in TYPES:
        raise GroundError(f'unknown type {a_type!r}; expected one of {TYPES}')

    item = Assumption(
        id=ground.next_id(),
        title=title,
        assumption=assumption,
        type=a_type,
        tier=tier or WORKING,
        evidence=evidence,
        created=_now(),
        last_validated=_now() if a_type == STATED else '',
    )
    if tier is None:
        if a_type == UNCERTAIN:
            item.tier = OPEN
        elif a_type == STATED:
            item.tier = ESTABLISHED
        elif item.high_impact:
            item.tier = OPEN
        else:
            item.tier = WORKING
    ground.assumptions.append(item)
    return item


def set_tier(ground: GroundFile, assumption_id: str, tier: str) -> Assumption:
    if tier not in TIERS:
        raise GroundError(f'unknown tier {tier!r}; expected one of {TIERS}')
    item = ground.get(assumption_id)
    if item is None:
        raise GroundError(f'no assumption with id {assumption_id!r}')
    item.tier = tier
    item.last_validated = _now()
    return item


def validate_all(ground: GroundFile) -> int:
    """Refresh the validation timestamp on every non-OPEN assumption.

    OPEN items are excluded deliberately: they were never validated, so marking
    them freshly validated would launder an unanswered question into a current
    one.
    """
    touched = 0
    for item in ground.assumptions:
        if item.tier != OPEN:
            item.last_validated = _now()
            touched += 1
    return touched


# --------------------------------------------------------------------------
# Premise checking — the enforcement surface
# --------------------------------------------------------------------------

@dataclass
class PremiseFinding:
    assumption_id: str
    title: str
    tier: str
    type: str
    severity: str
    message: str
    blocking: bool = False


def check(
    ground: GroundFile,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[PremiseFinding]:
    """Evaluate the ground file's own health, independent of any code change."""
    findings: list[PremiseFinding] = []

    for item in ground.by_tier(OPEN):
        blocking = item.high_impact
        findings.append(PremiseFinding(
            assumption_id=item.id,
            title=item.title,
            tier=item.tier,
            type=item.type,
            severity='High' if blocking else 'Medium',
            message=(
                'OPEN premise on a high-impact subject — validate before work '
                'depends on it' if blocking else
                'OPEN premise — validate before acting on it'
            ),
            blocking=blocking,
        ))

    for item in ground.assumptions:
        if item.tier != OPEN and item.is_stale(max_age_days):
            findings.append(PremiseFinding(
                assumption_id=item.id,
                title=item.title,
                tier=item.tier,
                type=item.type,
                severity='Low',
                message=(
                    f'not revalidated in {item.age_days()} days; '
                    f'{item.tier} confidence may no longer hold'
                ),
                blocking=False,
            ))

    for item in ground.assumptions:
        if item.tier == ESTABLISHED and item.type in (ASSUMED, UNCERTAIN):
            findings.append(PremiseFinding(
                assumption_id=item.id,
                title=item.title,
                tier=item.tier,
                type=item.type,
                severity='Medium',
                message=(
                    f'ESTABLISHED confidence resting on a {item.type!r} derivation — '
                    'a best-practice default or open question was promoted without '
                    'a stated basis'
                ),
                blocking=False,
            ))

    return findings


def open_premises(ground: GroundFile) -> list[dict]:
    """OPEN assumptions in the shape the verification gate consumes."""
    return [
        {
            'id': a.id,
            'title': a.title,
            'assumption': a.assumption,
            'high_impact': a.high_impact,
            'terms': _terms(a),
        }
        for a in ground.by_tier(OPEN)
    ]


def _terms(item: Assumption) -> list[str]:
    """Distinctive words for matching an assumption against verification text."""
    words = re.findall(r'[A-Za-z][A-Za-z0-9_.-]{3,}', f'{item.title} {item.assumption}')
    stop = {
        'this', 'that', 'with', 'from', 'have', 'will', 'should', 'must', 'need',
        'uses', 'used', 'using', 'been', 'were', 'they', 'them', 'than', 'then',
        'required', 'requires', 'project', 'code', 'file', 'files',
    }
    return sorted({w.lower() for w in words if w.lower() not in stop})


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _resolve(args) -> tuple[str, Optional[Path]]:
    pid = args.project_id or project_id(args.project_root)
    root = Path(args.store) if args.store else None
    return pid, root


def cmd_list(args) -> int:
    pid, root = _resolve(args)
    ground = load(pid, root)
    if args.json:
        print(json.dumps({
            'project_id': ground.project_id,
            'updated': ground.updated,
            'assumptions': [asdict(a) for a in ground.assumptions],
        }, indent=2))
        return 0
    if not ground.assumptions:
        print(f'No assumptions tracked for {pid}.')
        print('Run the /common-ground command to surface and record them.')
        return 0
    print(render_markdown(ground))
    return 0


def cmd_check(args) -> int:
    pid, root = _resolve(args)
    ground = load(pid, root)
    findings = check(ground, args.max_age_days)

    if args.json:
        print(json.dumps({
            'project_id': pid,
            'findings': [asdict(f) for f in findings],
            'blocking': any(f.blocking for f in findings),
        }, indent=2))
    else:
        print(f'Ground check — {pid}')
        print('=' * 68)
        counts = {tier: len(ground.by_tier(tier)) for tier in TIERS}
        print(f'ESTABLISHED {counts[ESTABLISHED]}   '
              f'WORKING {counts[WORKING]}   OPEN {counts[OPEN]}')
        print()
        if not findings:
            print('No premise findings.')
        for finding in findings:
            marker = 'BLOCK' if finding.blocking else ' warn'
            print(f'  [{marker}] {finding.assumption_id} · {finding.title}')
            print(f'          {finding.message}')
        print()
        print('Findings are reported per premise. No aggregate confidence score is')
        print('produced: one unvalidated high-impact premise is a blocked premise')
        print('regardless of how many others are established.')

    if any(f.blocking for f in findings):
        return 1
    return 2 if findings else 0


def cmd_add(args) -> int:
    pid, root = _resolve(args)
    ground = load(pid, root)
    item = add(ground, args.title, args.assumption, args.type, args.tier, args.evidence)
    md_path, index_path = save(ground, root)
    print(f'Added {item.id} [{item.type}] {item.tier} — {item.title}')
    print(f'  {md_path}')
    print(f'  {index_path}')
    return 0


def cmd_tier(args) -> int:
    pid, root = _resolve(args)
    ground = load(pid, root)
    try:
        item = set_tier(ground, args.id, args.tier)
    except GroundError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 3
    save(ground, root)
    print(f'{item.id} -> {item.tier}  (type {item.type} unchanged — types are immutable)')
    return 0


def cmd_validate(args) -> int:
    pid, root = _resolve(args)
    ground = load(pid, root)
    touched = validate_all(ground)
    save(ground, root)
    print(f'Revalidated {touched} assumption(s). OPEN items were not touched: an')
    print('unanswered question does not become current by being timestamped.')
    return 0


def cmd_premises(args) -> int:
    pid, root = _resolve(args)
    ground = load(pid, root)
    print(json.dumps(open_premises(ground), indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Track and check the project assumptions work is built on.',
    )
    parser.add_argument('--project-root', default='.', help='Project directory')
    parser.add_argument('--project-id', help='Override the derived project id')
    parser.add_argument('--store', help='Ground file store root (default ~/.claude/common-ground)')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('list', help='Show tracked assumptions')
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('check', help='Report premise findings')
    p.add_argument('--json', action='store_true')
    p.add_argument('--max-age-days', type=int, default=DEFAULT_MAX_AGE_DAYS)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser('add', help='Record an assumption')
    p.add_argument('title')
    p.add_argument('assumption')
    p.add_argument('--type', required=True, choices=TYPES)
    p.add_argument('--tier', choices=TIERS, help='Omit to derive from type and impact')
    p.add_argument('--evidence', default='')
    p.set_defaults(func=cmd_add)

    p = sub.add_parser('tier', help='Change an assumption\'s tier (never its type)')
    p.add_argument('id')
    p.add_argument('tier', choices=TIERS)
    p.set_defaults(func=cmd_tier)

    p = sub.add_parser('validate', help='Refresh validation timestamps on non-OPEN items')
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser('premises', help='Emit OPEN premises as JSON for the gate')
    p.set_defaults(func=cmd_premises)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    from _cli import guard_broken_pipe
    guard_broken_pipe(main)
