#!/usr/bin/env python3
"""
Work Items — local, file-based epic and ticket tracking.

The outer project lifecycle needs somewhere to keep work items. The lineage this
was adapted from used a hosted tracker; this implementation is local files and
CLI only, so the suite has no third-party dependency and a project's work items
live in the repository beside the code they describe.

Storage is markdown with YAML-ish frontmatter, plus a generated JSON index:

    .dev-suite/work/
    ├── index.json               generated; never hand-edited
    ├── EPIC-1/
    │   ├── epic.md
    │   ├── T-1.md
    │   └── T-2.md

Markdown is the source of truth and the index is derived, because a human
editing a ticket in their editor should never be silently overwritten by a tool
that considers its own cache authoritative.

Tickets declare dependencies by id. ``waves`` computes a topological order and
groups independent tickets into parallel execution waves. A dependency cycle is
reported as a cycle, not silently broken — an arbitrary order through a cycle
produces work done in the wrong sequence with no indication anything is wrong.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORK_DIRNAME = Path('.dev-suite') / 'work'

# Ticket lifecycle. Deliberately short: every extra state is one more thing that
# can be wrong, and this tracker exists to sequence work, not to model process.
TODO = 'todo'
IN_PROGRESS = 'in-progress'
IN_REVIEW = 'in-review'
DONE = 'done'
BLOCKED = 'blocked'
STATUSES = (TODO, IN_PROGRESS, IN_REVIEW, DONE, BLOCKED)

TERMINAL = frozenset({DONE})

FRONTMATTER = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.S)


class WorkItemError(ValueError):
    """Raised on an invalid item, an unknown id, or a dependency cycle."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class Ticket:
    id: str
    title: str
    epic: str
    status: str = TODO
    depends_on: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    body: str = ''
    created: str = ''
    updated: str = ''

    def __post_init__(self):
        if self.status not in STATUSES:
            raise WorkItemError(
                f'ticket {self.id}: unknown status {self.status!r}; expected {STATUSES}'
            )

    @property
    def complete(self) -> bool:
        return self.status in TERMINAL

    @property
    def gaps(self) -> list[str]:
        """What stops this ticket being picked up without reading anything else.

        Reported as distinct causes rather than one boolean, so the message
        names the actual gap. A ticket missing acceptance criteria and a ticket
        missing a description are different problems with different fixes.
        """
        missing = []
        if not self.acceptance:
            missing.append(
                'no acceptance criteria — nothing defines finished, so any '
                'output can be argued to satisfy it'
            )
        if not self.body.strip():
            missing.append(
                'no description — an executing agent would have to infer the '
                'work from the title alone'
            )
        return missing

    @property
    def self_contained(self) -> bool:
        """Whether this ticket can be picked up without reading anything else."""
        return not self.gaps


@dataclass
class Epic:
    id: str
    title: str
    status: str = TODO
    body: str = ''
    created: str = ''
    updated: str = ''
    tickets: list[Ticket] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.tickets) and all(t.complete for t in self.tickets)

    def progress(self) -> tuple[int, int]:
        return sum(1 for t in self.tickets if t.complete), len(self.tickets)


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    raw, body = match.groups()
    data: dict = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith('#'):
            continue
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip()
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            data[key] = [v.strip().strip('"\'') for v in inner.split(',') if v.strip()]
        else:
            data[key] = value.strip('"\'')
    return data, body


def _render_frontmatter(pairs: dict) -> str:
    lines = ['---']
    for key, value in pairs.items():
        if isinstance(value, list):
            rendered = ', '.join(value)
            lines.append(f'{key}: [{rendered}]')
        else:
            lines.append(f'{key}: {value}')
    lines.append('---')
    return '\n'.join(lines)


def _ticket_from_file(path: Path, epic_id: str) -> Ticket:
    data, body = _parse_frontmatter(path.read_text(encoding='utf-8'))
    acceptance = data.get('acceptance', [])
    if isinstance(acceptance, str):
        acceptance = [acceptance] if acceptance else []
    if not acceptance:
        acceptance = re.findall(r'(?m)^\s*-\s*\[[ x]\]\s*(.+)$', body)
    return Ticket(
        id=data.get('id', path.stem),
        title=data.get('title', path.stem),
        epic=data.get('epic', epic_id),
        status=data.get('status', TODO),
        depends_on=data.get('depends_on', []) or [],
        acceptance=acceptance,
        files=data.get('files', []) or [],
        body=body.strip(),
        created=data.get('created', ''),
        updated=data.get('updated', ''),
    )


def _write_ticket(path: Path, ticket: Ticket) -> None:
    ticket.updated = _now()
    header = _render_frontmatter({
        'id': ticket.id,
        'title': ticket.title,
        'epic': ticket.epic,
        'status': ticket.status,
        'depends_on': ticket.depends_on,
        'files': ticket.files,
        'created': ticket.created or _now(),
        'updated': ticket.updated,
    })
    body = ticket.body.strip()
    if ticket.acceptance and '- [ ]' not in body and '- [x]' not in body:
        criteria = '\n'.join(f'- [ ] {c}' for c in ticket.acceptance)
        body = f'{body}\n\n## Acceptance criteria\n\n{criteria}'.strip()
    path.write_text(f'{header}\n\n{body}\n', encoding='utf-8')


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

def work_dir(project_root: str) -> Path:
    return Path(project_root) / WORK_DIRNAME


def load_all(project_root: str) -> list[Epic]:
    """Read every epic and ticket from disk. Markdown is the source of truth."""
    base = work_dir(project_root)
    if not base.is_dir():
        return []

    epics: list[Epic] = []
    for epic_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        epic_file = epic_dir / 'epic.md'
        if not epic_file.is_file():
            continue
        data, body = _parse_frontmatter(epic_file.read_text(encoding='utf-8'))
        epic = Epic(
            id=data.get('id', epic_dir.name),
            title=data.get('title', epic_dir.name),
            status=data.get('status', TODO),
            body=body.strip(),
            created=data.get('created', ''),
            updated=data.get('updated', ''),
        )
        for ticket_file in sorted(epic_dir.glob('*.md')):
            if ticket_file.name == 'epic.md':
                continue
            epic.tickets.append(_ticket_from_file(ticket_file, epic.id))
        epics.append(epic)
    return epics


def find_epic(project_root: str, epic_id: str) -> Epic:
    for epic in load_all(project_root):
        if epic.id == epic_id:
            return epic
    raise WorkItemError(f'no epic with id {epic_id!r}')


def find_ticket(project_root: str, ticket_id: str) -> tuple[Epic, Ticket]:
    for epic in load_all(project_root):
        for ticket in epic.tickets:
            if ticket.id == ticket_id:
                return epic, ticket
    raise WorkItemError(f'no ticket with id {ticket_id!r}')


def write_index(project_root: str) -> Path:
    """Regenerate the derived JSON index from the markdown on disk."""
    base = work_dir(project_root)
    base.mkdir(parents=True, exist_ok=True)
    epics = load_all(project_root)
    index_path = base / 'index.json'
    index_path.write_text(
        json.dumps(
            {
                'generated': _now(),
                'note': 'Derived from the markdown files. Edit those, not this.',
                'epics': [
                    {
                        **{k: v for k, v in asdict(e).items() if k != 'tickets'},
                        'tickets': [asdict(t) for t in e.tickets],
                    }
                    for e in epics
                ],
            },
            indent=2,
        ),
        encoding='utf-8',
    )
    return index_path


def _next_id(existing: list[str], prefix: str) -> str:
    used = set()
    for item in existing:
        match = re.fullmatch(rf'{re.escape(prefix)}-(\d+)', item)
        if match:
            used.add(int(match.group(1)))
    return f'{prefix}-{(max(used) + 1) if used else 1}'


def create_epic(project_root: str, title: str, body: str = '') -> Epic:
    epics = load_all(project_root)
    epic_id = _next_id([e.id for e in epics], 'EPIC')
    directory = work_dir(project_root) / epic_id
    directory.mkdir(parents=True, exist_ok=True)
    header = _render_frontmatter({
        'id': epic_id, 'title': title, 'status': TODO,
        'created': _now(), 'updated': _now(),
    })
    (directory / 'epic.md').write_text(f'{header}\n\n{body.strip()}\n', encoding='utf-8')
    write_index(project_root)
    return Epic(id=epic_id, title=title, body=body, created=_now())


def create_ticket(
    project_root: str,
    epic_id: str,
    title: str,
    body: str = '',
    depends_on: Optional[list[str]] = None,
    acceptance: Optional[list[str]] = None,
    files: Optional[list[str]] = None,
) -> Ticket:
    epic = find_epic(project_root, epic_id)
    all_ids = [t.id for e in load_all(project_root) for t in e.tickets]
    ticket = Ticket(
        id=_next_id(all_ids, 'T'),
        title=title,
        epic=epic.id,
        depends_on=depends_on or [],
        acceptance=acceptance or [],
        files=files or [],
        body=body,
        created=_now(),
    )
    unknown = [d for d in ticket.depends_on if d not in all_ids]
    if unknown:
        raise WorkItemError(
            f'ticket depends on unknown id(s): {", ".join(unknown)}. '
            'Create the dependency first, or the execution order will be wrong.'
        )
    _write_ticket(work_dir(project_root) / epic.id / f'{ticket.id}.md', ticket)
    write_index(project_root)
    return ticket


def set_status(project_root: str, ticket_id: str, status: str) -> Ticket:
    if status not in STATUSES:
        raise WorkItemError(f'unknown status {status!r}; expected {STATUSES}')
    epic, ticket = find_ticket(project_root, ticket_id)

    if status in (IN_PROGRESS, IN_REVIEW, DONE):
        blockers = [
            d for d in ticket.depends_on
            if not _is_complete(project_root, d)
        ]
        if blockers:
            raise WorkItemError(
                f'{ticket_id} depends on incomplete ticket(s): {", ".join(blockers)}. '
                'Starting out of order is how a dependency gets built on top of '
                'work that has not landed.'
            )

    ticket.status = status
    _write_ticket(work_dir(project_root) / epic.id / f'{ticket.id}.md', ticket)
    write_index(project_root)
    return ticket


def _is_complete(project_root: str, ticket_id: str) -> bool:
    try:
        _, ticket = find_ticket(project_root, ticket_id)
    except WorkItemError:
        return False
    return ticket.complete


# --------------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------------

def waves(epic: Epic) -> list[list[Ticket]]:
    """Group tickets into parallel execution waves by dependency depth.

    Every ticket in a wave is independent of every other in that wave, so a
    wave can be executed concurrently. Raises on a cycle rather than emitting
    an arbitrary order.
    """
    by_id = {t.id: t for t in epic.tickets}
    remaining = dict(by_id)
    placed: set[str] = set()
    result: list[list[Ticket]] = []

    while remaining:
        ready = [
            ticket for ticket in remaining.values()
            if all(dep in placed or dep not in by_id for dep in ticket.depends_on)
        ]
        if not ready:
            cycle = ', '.join(sorted(remaining))
            raise WorkItemError(
                f'dependency cycle among: {cycle}. No execution order exists; '
                'break the cycle rather than picking an arbitrary sequence.'
            )
        ready.sort(key=lambda t: t.id)
        result.append(ready)
        for ticket in ready:
            placed.add(ticket.id)
            del remaining[ticket.id]
    return result


def next_ready(epic: Epic) -> list[Ticket]:
    """Tickets that can be started right now."""
    done = {t.id for t in epic.tickets if t.complete}
    return [
        t for t in epic.tickets
        if t.status == TODO and all(d in done for d in t.depends_on)
    ]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_init(args) -> int:
    base = work_dir(args.project_root)
    base.mkdir(parents=True, exist_ok=True)
    index = write_index(args.project_root)
    print(f'Work item store ready: {base}')
    print(f'Index: {index}')
    return 0


def cmd_epic(args) -> int:
    epic = create_epic(args.project_root, args.title, args.body or '')
    print(f'Created {epic.id} — {epic.title}')
    print(f'  {work_dir(args.project_root) / epic.id / "epic.md"}')
    return 0


def cmd_ticket(args) -> int:
    try:
        ticket = create_ticket(
            args.project_root, args.epic, args.title, args.body or '',
            depends_on=args.depends_on, acceptance=args.acceptance, files=args.files,
        )
    except WorkItemError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 3
    print(f'Created {ticket.id} — {ticket.title}  (epic {ticket.epic})')
    for gap in ticket.gaps:
        print(f'  warning: {gap}')
    return 0


def cmd_status(args) -> int:
    try:
        ticket = set_status(args.project_root, args.id, args.status)
    except WorkItemError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(f'{ticket.id} -> {ticket.status}')
    return 0


def cmd_list(args) -> int:
    epics = load_all(args.project_root)
    if args.json:
        print(json.dumps([
            {**{k: v for k, v in asdict(e).items() if k != 'tickets'},
             'tickets': [asdict(t) for t in e.tickets]}
            for e in epics
        ], indent=2))
        return 0
    if not epics:
        print('No work items. Run: work_items.py epic "<title>"')
        return 0
    for epic in epics:
        done, total = epic.progress()
        print(f'{epic.id}  {epic.title}   [{done}/{total} complete]')
        for ticket in epic.tickets:
            deps = f'  depends on {", ".join(ticket.depends_on)}' if ticket.depends_on else ''
            flag = '' if ticket.self_contained else f'  ({len(ticket.gaps)} gap(s))'
            print(f'   {ticket.id:<6} {ticket.status:<12} {ticket.title}{deps}{flag}')
        print()
    return 0


def cmd_waves(args) -> int:
    try:
        epic = find_epic(args.project_root, args.epic)
        grouped = waves(epic)
    except WorkItemError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(
            [[asdict(t) for t in wave] for wave in grouped], indent=2))
        return 0

    print(f'Execution waves — {epic.id} {epic.title}')
    print('=' * 68)
    for number, wave in enumerate(grouped, start=1):
        print(f'Wave {number}  ({len(wave)} ticket(s), independent — may run in parallel)')
        for ticket in wave:
            print(f'   {ticket.id:<6} {ticket.status:<12} {ticket.title}')
        print()
    ready = next_ready(epic)
    print('Ready to start now: ' + (', '.join(t.id for t in ready) if ready else 'none'))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Local file-based epic and ticket tracking. No external services.',
    )
    parser.add_argument('--project-root', default='.', help='Project root directory')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('init', help='Create the work item store')
    p.set_defaults(func=cmd_init)

    p = sub.add_parser('epic', help='Create an epic')
    p.add_argument('title')
    p.add_argument('--body', default='')
    p.set_defaults(func=cmd_epic)

    p = sub.add_parser('ticket', help='Create a ticket under an epic')
    p.add_argument('epic')
    p.add_argument('title')
    p.add_argument('--body', default='')
    p.add_argument('--depends-on', nargs='*', default=[])
    p.add_argument('--acceptance', nargs='*', default=[])
    p.add_argument('--files', nargs='*', default=[])
    p.set_defaults(func=cmd_ticket)

    p = sub.add_parser('status', help='Set a ticket status')
    p.add_argument('id')
    p.add_argument('status', choices=STATUSES)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser('list', help='List epics and tickets')
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('waves', help='Show parallel execution waves for an epic')
    p.add_argument('epic')
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_waves)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    from _cli import guard_broken_pipe
    guard_broken_pipe(main)
