#!/usr/bin/env python3
"""
Review Packet — assembles and verifies the only thing a reviewer may see.

A reviewer that reads the author's reasoning is not an independent reviewer. It
is a second opinion on an argument it has already been given, and it agrees far
more often than the code deserves. The failure is not that the reviewer is
careless; it is that "here is what I did and why" is a frame, and a frame is
very hard to review your way out of. The author's confidence transfers, their
blind spots transfer, and the review comes back approving the thing the author
was already sure about.

So the reviewer is handed exactly two things:

  * **the original task** — verbatim, as recorded before any work started
  * **the completed work** — the diff, and nothing about how it came to exist

Everything else is withheld: the thought process, the intermediate steps, the
tool calls, the author's own verification block, the author's assessment of
their own output. The reviewer forms its judgment from the task and the artifact
alone, the same way a reviewer who joined the project this morning would.

The task is recorded *before* work begins and pinned by hash. This is the rule
that does the most work, and the least obvious one. An orchestrator that has
been deep in the problem does not paraphrase neutrally — "review the caching fix
for the race condition" already tells the reviewer what to find and what to
conclude. Pinning the task means the reviewer reads the request as the requester
wrote it, not as the author came to understand it.

Two commands, two jobs:

  * ``record`` — pin the original task before work starts
  * ``build``  — assemble a packet from the pinned task and a diff
  * ``check``  — verify a packet carries nothing but those two things

``check`` exists separately from ``build`` because a packet assembled by hand,
or by a workflow this script never saw, still has to be checkable. Enforcement
that only works when you used the right tool is not enforcement.

Exit codes: ``0`` clean · ``1`` contaminated · ``3`` unusable input.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

STATE_DIR_NAME = '.dev-suite'
REVIEW_DIR_NAME = 'review'
TASK_FILENAME = 'task.json'

PACKET_VERSION = 1
HEADER_OPEN = '<!-- dev-suite review packet v1'
HEADER_CLOSE = '-->'

TASK_HEADING = '## Task'
WORK_HEADING = '## Work'

CLEAN = 0
CONTAMINATED = 1
UNUSABLE = 3


# --------------------------------------------------------------------------
# Contamination rules
# --------------------------------------------------------------------------
#
# Each rule names one way the author's process reaches the reviewer. They are
# separate rules rather than one "looks like narrative" heuristic because the
# report has to tell the caller which line to remove, and because a rule nobody
# can name is a rule nobody maintains.
#
# Every pattern below is matched only against *prose* — text outside fenced
# code blocks. The work section is a diff, and a diff legitimately contains
# `I` in a string literal, `PASS` in a test name, and `verified` in a comment.
# Scanning the artifact for words about the artifact is how a checker like this
# ends up rejecting correct packets and getting switched off.

@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    explanation: str


RULES: tuple[Rule, ...] = (
    Rule(
        'author_narrative',
        re.compile(
            r'\b('
            r'I (?:implemented|added|chose|decided|refactored|opted|went with|'
            r'considered|realised|realized|started|ended up|had to|think|believe)'
            r'|my (?:approach|reasoning|implementation|change|fix|plan|thinking)'
            r'|(?:first|then|next|finally),? I\b'
            r'|as (?:discussed|mentioned|noted) (?:above|earlier|previously)'
            r'|we (?:decided|chose|agreed)'
            r')',
            re.IGNORECASE,
        ),
        'the author narrating how the work came about — the reviewer forms its '
        'own account of what the diff does',
    ),
    Rule(
        'verification_block',
        re.compile(
            r'(?im)^#{1,6}\s*(?:pre-?output\s+verification|delivery\s+gate|'
            r'verification)\b'
            r'|\b(?:OBSERVED|CLAIMED|CONTRADICTED|UNVERIFIED)\b\s*[|—:-]',
        ),
        "the author's own verification block — its claims about the work are "
        'exactly what an independent review exists to test',
    ),
    Rule(
        'self_assessment',
        re.compile(
            r'\b('
            r'(?:all|every) (?:tests?|checks?) pass(?:ed|es)?'
            r'|this (?:is|should be) correct'
            r'|(?:i|we) (?:have )?(?:verified|confirmed|tested|validated)'
            r'|no (?:issues|problems|bugs) (?:found|remain)'
            r'|(?:looks|works) (?:good|fine|correct)'
            r'|ready (?:for|to) (?:merge|ship|review)'
            r')',
            re.IGNORECASE,
        ),
        "the author's verdict on their own work — a reviewer told the answer "
        'reviews toward it',
    ),
    Rule(
        'process_reference',
        re.compile(
            r'('
            r'\.dev-suite/'
            r'|\btranscript\b'
            r'|\bsession[ _-]log\b'
            r'|\btool call\b'
            r'|\bsubagent\b'
            r'|\bmy earlier\b'
            r'|\bprevious (?:turn|attempt|iteration)\b'
            r')',
            re.IGNORECASE,
        ),
        'a pointer into the work process — the reviewer must not be able to '
        'follow it, and must not know it exists',
    ),
)


@dataclass
class Finding:
    rule: str
    line: int
    text: str
    explanation: str


# --------------------------------------------------------------------------
# Hashing and recorded task
# --------------------------------------------------------------------------

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def review_dir(project_root: str) -> Path:
    return Path(project_root) / STATE_DIR_NAME / REVIEW_DIR_NAME


def task_path(project_root: str) -> Path:
    return review_dir(project_root) / TASK_FILENAME


def record_task(project_root: str, task: str) -> dict:
    """Pin the original task. Refuses to overwrite an existing record.

    Overwriting would defeat the point: a task re-recorded after the work is
    done is the author's summary of what they built, which is the framing this
    module exists to keep out of the reviewer's hands. Re-recording is possible
    but has to be deliberate — delete the file.
    """
    task = task.strip()
    if not task:
        raise ValueError('refusing to record an empty task')

    path = task_path(project_root)
    if path.exists():
        existing = json.loads(path.read_text(encoding='utf-8'))
        if existing.get('sha256') != sha256(task):
            raise ValueError(
                f'a different task is already recorded at {path}. A task '
                're-recorded mid-work is the author\'s summary, not the '
                'request. Delete the file to start a new unit of work.'
            )
        return existing

    record = {
        'version': PACKET_VERSION,
        'task': task,
        'sha256': sha256(task),
        'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def load_task(project_root: str) -> dict:
    path = task_path(project_root)
    if not path.exists():
        raise FileNotFoundError(
            f'no task recorded at {path}. Record the original task before work '
            'begins — a task written afterwards has already been shaped by the '
            'work. Run: review_packet.py record <project_root> --task-file <f>'
        )
    return json.loads(path.read_text(encoding='utf-8'))


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def fence_for(*bodies: str) -> str:
    """A fence longer than any backtick run inside the content it wraps.

    Tasks get pasted out of issue trackers and diffs touch Markdown files, so
    both sections routinely contain their own code fences. A fixed three
    backticks would be closed by the first one of those, and everything after
    it would be read as packet structure.
    """
    longest = 0
    for body in bodies:
        for run in re.findall(r'`+', body):
            longest = max(longest, len(run))
    return '`' * max(3, longest + 1)


def build_packet(task_record: dict, work: str) -> str:
    """Assemble the packet.

    Both sections are fenced. For the work that keeps the artifact from being
    scanned as though it were narrative. For the task it keeps the requester's
    own Markdown from being read as packet structure: a bug report opening with
    ``## Steps to reproduce`` is an ordinary task, and an unfenced packet would
    reject it as an extra section — failing closed on a request that was
    recorded exactly right.
    """
    work = work.rstrip('\n')
    if not work.strip():
        raise ValueError('refusing to build a packet with no work in it')

    task = task_record['task'].strip()
    fence = fence_for(task, work)

    header = '\n'.join([
        HEADER_OPEN,
        f'task_sha256: {task_record["sha256"]}',
        f'work_sha256: {sha256(work)}',
        f'built: {datetime.now(timezone.utc).isoformat(timespec="seconds")}',
        HEADER_CLOSE,
    ])
    return '\n'.join([
        header,
        '',
        TASK_HEADING,
        '',
        f'{fence}text',
        task,
        fence,
        '',
        WORK_HEADING,
        '',
        f'{fence}diff',
        work,
        fence,
        '',
    ])


# --------------------------------------------------------------------------
# Checking
# --------------------------------------------------------------------------

def parse_header(text: str) -> dict:
    """Read the packet header. Absent or malformed is not fatal on its own —
    a hand-assembled packet has no header, and the section and prose rules
    still apply to it."""
    if not text.lstrip().startswith(HEADER_OPEN):
        return {}
    body = text.split(HEADER_OPEN, 1)[1].split(HEADER_CLOSE, 1)[0]
    fields = {}
    for line in body.splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            fields[key.strip()] = value.strip()
    return fields


def _fence_spans(lines: list[str]) -> list[tuple[int, int]]:
    """Index ranges (open, close) of fenced blocks, inclusive of both markers.

    CommonMark: a fence opens with three or more backticks and is closed by a
    line of at least as many. Tracking the opening length matters here — the
    builder deliberately uses a longer fence when the content contains one, so
    a fixed-length reader would close the block at the wrong line.
    """
    spans: list[tuple[int, int]] = []
    open_at: Optional[int] = None
    open_len = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('```'):
            continue
        run = len(stripped) - len(stripped.lstrip('`'))
        if open_at is None:
            open_at, open_len = i, run
        elif run >= open_len and stripped == '`' * run:
            spans.append((open_at, i))
            open_at, open_len = None, 0
    if open_at is not None:
        spans.append((open_at, len(lines) - 1))   # unterminated: treat as fenced
    return spans


def _in_span(index: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= index <= end for start, end in spans)


def prose_lines(lines: list[str]) -> list[tuple[int, str]]:
    """1-based numbered lines outside every fenced block."""
    spans = _fence_spans(lines)
    return [(i + 1, line) for i, line in enumerate(lines) if not _in_span(i, spans)]


def headings(lines: list[str]) -> list[tuple[int, str]]:
    """Headings outside fenced blocks — the packet's structure.

    A ``##`` inside a fence is content: either the requester's own Markdown or
    a changed Markdown file in the diff. Neither is a packet section.
    """
    spans = _fence_spans(lines)
    return [
        (i + 1, line.strip())
        for i, line in enumerate(lines)
        if not _in_span(i, spans) and re.match(r'^#{1,6}\s', line)
    ]


def section_body(lines: list[str], heading: str) -> str:
    """Content of one section, with its wrapping fence removed if it has one.

    Runs to the next *structural* heading, so a heading inside the section's
    own fenced content does not truncate it.
    """
    structure = headings(lines)
    start = next((n for n, h in structure if h == heading), None)
    if start is None:
        return ''
    later = [n for n, _ in structure if n > start]
    end = (later[0] - 1) if later else len(lines)
    body = lines[start:end]           # start is 1-based, so this skips the heading

    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    if body and body[0].strip().startswith('```'):
        opener = body[0].strip()
        run = len(opener) - len(opener.lstrip('`'))
        if body[-1].strip() == '`' * run:
            body = body[1:-1]
    return '\n'.join(body).strip()


def check_packet(
    text: str,
    task_record: Optional[dict] = None,
) -> list[Finding]:
    """Return every way this packet exposes more than task and artifact."""
    findings: list[Finding] = []
    lines = text.splitlines()

    # -- structure ---------------------------------------------------------
    found_headings = headings(lines)
    heading_texts = [h for _, h in found_headings]

    for number, heading in found_headings:
        if heading not in (TASK_HEADING, WORK_HEADING):
            findings.append(Finding(
                'extra_section', number, heading,
                'a packet has exactly two sections; anything else is context '
                'the reviewer was not meant to have',
            ))

    for required in (TASK_HEADING, WORK_HEADING):
        if required not in heading_texts:
            findings.append(Finding(
                'missing_section', 0, required,
                'without both sections there is nothing to review against',
            ))

    # -- task integrity ----------------------------------------------------
    header = parse_header(text)
    task_text = section_body(lines, TASK_HEADING)
    work_text = section_body(lines, WORK_HEADING)

    if task_text:
        actual = sha256(task_text)
        declared = header.get('task_sha256')
        if declared and declared != actual:
            findings.append(Finding(
                'task_tampering', 0, f'declared {declared[:12]}, actual {actual[:12]}',
                'the task text does not match the hash the packet declares',
            ))
        if task_record and task_record.get('sha256') != actual:
            findings.append(Finding(
                'task_tampering', 0, f'recorded {task_record["sha256"][:12]}, '
                f'packet {actual[:12]}',
                'the packet restates the task rather than quoting it. A '
                'rewritten task tells the reviewer what to conclude',
            ))

    # -- work integrity ----------------------------------------------------
    #
    # Declaring a hash and never checking it is worse than declaring nothing:
    # it reads as integrity that is not enforced. The realistic failure is not
    # tampering but staleness — a packet built early, work continued, packet
    # never rebuilt — and the reviewer then passes an artifact that no longer
    # exists.
    declared_work = header.get('work_sha256')
    if declared_work and work_text:
        actual_work = sha256(work_text)
        if declared_work != actual_work:
            findings.append(Finding(
                'work_tampering', 0,
                f'declared {declared_work[:12]}, actual {actual_work[:12]}',
                'the work in the packet is not the work the packet was built '
                'from — the reviewer would be reviewing a different diff, or a '
                'stale one, from the one the packet claims',
            ))

    # -- prose contamination ----------------------------------------------
    #
    # Fenced content is exempt. For the work that is the artifact; for the task
    # it is the requester's own words, pinned by hash before work began and
    # cross-checked above, so it cannot be a channel for the author's framing.
    for number, line in prose_lines(lines):
        stripped = line.strip()
        if not stripped or stripped in (TASK_HEADING, WORK_HEADING):
            continue
        if stripped.startswith('<!--') or stripped.startswith('task_sha256') \
                or stripped.startswith('work_sha256') or stripped.startswith('built:') \
                or stripped == HEADER_CLOSE:
            continue
        for rule in RULES:
            if rule.pattern.search(stripped):
                findings.append(Finding(
                    rule.name, number, stripped[:160], rule.explanation,
                ))
                break

    return findings


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def render(findings: list[Finding], source: str) -> str:
    out = [
        'Review Packet Check',
        '=' * 68,
        f'Source   : {source}',
        f'Decision : {"CONTAMINATED" if findings else "CLEAN"}',
        '',
    ]
    if not findings:
        out.append('The packet carries the original task and the completed work.')
        out.append('Nothing about how the work was produced reached it.')
        return '\n'.join(out)

    out.append(f'{len(findings)} disclosure(s) the reviewer must not see:')
    out.append('')
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule, []).append(f)
    for rule, group in by_rule.items():
        out.append(f'  {rule} — {group[0].explanation}')
        for f in group:
            where = f'line {f.line}' if f.line else 'packet'
            out.append(f'      {where}: {f.text}')
        out.append('')
    out.append('Remove these lines and rebuild. Do not summarise them for the')
    out.append('reviewer instead — a summary of the process is still the process.')
    return '\n'.join(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8', errors='replace')


def cmd_record(args: argparse.Namespace) -> int:
    task = _read(args.task_file) if args.task_file else (args.task or '')
    try:
        record = record_task(args.project_root, task)
    except (ValueError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return UNUSABLE
    if args.json:
        print(json.dumps(record, indent=2))
    else:
        print(f'task recorded: {task_path(args.project_root)}')
        print(f'sha256: {record["sha256"]}')
    return CLEAN


def cmd_build(args: argparse.Namespace) -> int:
    try:
        record = load_task(args.project_root)
        work = _read(args.diff)
        packet = build_packet(record, work)
    except (ValueError, OSError, FileNotFoundError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return UNUSABLE

    # Check what we just built. A builder that cannot fail its own output is
    # a builder nobody checks — and the diff itself can carry a stray
    # verification block the author pasted into a file.
    findings = check_packet(packet, record)
    if findings:
        print(render(findings, 'freshly built packet'), file=sys.stderr)
        print('\npacket not written — the material above would have reached the '
              'reviewer', file=sys.stderr)
        return CONTAMINATED

    if args.output:
        Path(args.output).write_text(packet, encoding='utf-8')
        print(f'packet written: {args.output}')
    else:
        sys.stdout.write(packet)
    return CLEAN


def cmd_check(args: argparse.Namespace) -> int:
    try:
        text = _read(args.packet)
    except OSError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return UNUSABLE

    record = None
    if args.project_root:
        try:
            record = load_task(args.project_root)
        except (OSError, FileNotFoundError, ValueError):
            record = None  # cross-check is a bonus; structural rules still apply

    findings = check_packet(text, record)
    if args.json:
        print(json.dumps({
            'decision': 'CONTAMINATED' if findings else 'CLEAN',
            'findings': [asdict(f) for f in findings],
        }, indent=2))
    else:
        print(render(findings, args.packet))
    return CONTAMINATED if findings else CLEAN


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Assemble and verify the packet an independent reviewer sees.',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    p_record = sub.add_parser(
        'record', help='Pin the original task before work begins')
    p_record.add_argument('project_root')
    group = p_record.add_mutually_exclusive_group(required=True)
    group.add_argument('--task-file', help='File holding the original task')
    group.add_argument('--task', help='The original task, verbatim')
    p_record.add_argument('--json', action='store_true')
    p_record.set_defaults(func=cmd_record)

    p_build = sub.add_parser(
        'build', help='Assemble a packet from the pinned task and a diff')
    p_build.add_argument('project_root')
    p_build.add_argument('--diff', required=True, help='File holding the diff')
    p_build.add_argument('-o', '--output', help='Write here instead of stdout')
    p_build.set_defaults(func=cmd_build)

    p_check = sub.add_parser(
        'check', help='Verify a packet exposes only task and artifact')
    p_check.add_argument('packet')
    p_check.add_argument(
        '--project-root',
        help='Cross-check the packet task against the recorded original')
    p_check.add_argument('--json', action='store_true')
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    from _cli import guard_broken_pipe
    guard_broken_pipe(main)
