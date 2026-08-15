#!/usr/bin/env python3
"""
Verification Gate — enforcement for agent pre-output verification blocks.

A verification block is only a gate if something checks it. Without enforcement
an agent can write PASS across the board and the block becomes decoration. This
script parses the block an agent produced and applies the rules that a prose
checklist cannot enforce on itself:

  1. CONTRADICTED on any item blocks delivery.
  2. UNVERIFIED on a security-sensitive item blocks delivery.
  3. Status inflation — OBSERVED asserted on naming/comment/documentation/
     inference evidence — is downgraded to CLAIMED and reported. Tiers 8-10
     cannot support OBSERVED.
  4. Aggregate pass scores ("6/7", "86%") invalidate the block. Averaging lets
     a critical failure hide behind cosmetic successes.
  5. Literal secrets in evidence text are redacted before reporting and flagged.
  6. Missing items and missing limitations statements are reported, not assumed
     benign.

Both block formats are accepted: the plain PASS/FAIL checklist and the full
evidence table. Format is auto-detected.

The output is per-item. This script deliberately emits no overall score.

Exit codes:  0 = approved   1 = blocked   2 = approved with warnings
             3 = block could not be parsed (treated as blocking by callers)

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

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

OBSERVED = 'OBSERVED'
INFERRED = 'INFERRED'
CLAIMED = 'CLAIMED'
UNVERIFIED = 'UNVERIFIED'
CONTRADICTED = 'CONTRADICTED'

EVIDENCE_STATUSES = {OBSERVED, INFERRED, CLAIMED, UNVERIFIED, CONTRADICTED}
PLAIN_STATUSES = {'PASS', 'FAIL'}
ALL_STATUSES = EVIDENCE_STATUSES | PLAIN_STATUSES

APPROVE = 'approve'
BLOCK = 'block'

# Evidence quality hierarchy: tier 1 strongest, tier 10 weakest.
# Tiers 8-10 cannot support an OBSERVED status.
EVIDENCE_TIERS: list[tuple[int, str, tuple[str, ...]]] = [
    (1, 'reproduced runtime behaviour',
     ('reproduced', 'runtime behaviour', 'runtime behavior', 'ran the app',
      'executed the endpoint', 'observed at runtime')),
    (2, 'automated test result',
     ('test passed', 'tests pass', 'pytest', 'jest', 'vitest', 'test suite',
      'unit test', 'integration test', 'npm test')),
    (3, 'direct source-code evidence',
     ('read the file', 'source read', 'read src', 'inspected the source',
      'grepped', 'file was read', 'read directly', 'line ')),
    (4, 'configuration / dependency manifest',
     ('package.json', 'requirements.txt', 'pyproject', 'go.mod', 'cargo.toml',
      'manifest', 'lockfile', 'package-lock')),
    (5, 'build / CI evidence',
     ('tsc --noemit', 'tsc ', 'build passed', 'compiled', 'mypy', 'eslint',
      'ruff', 'ci passed', 'exit 0', 'lint clean')),
    (6, 'version-control evidence',
     ('git diff', 'git log', 'commit ', 'branch ', 'git blame')),
    (7, 'documentation',
     ('docs say', 'documentation', 'per the docs', 'readme', 'api reference')),
    (8, 'comments',
     ('comment says', 'the comment', 'docstring says', 'per the comment')),
    (9, 'naming / convention',
     ('naming', 'name suggests', 'looks right', 'follows the convention',
      'similar pattern', 'sibling module', 'probably exists', 'seems to exist',
      'consistent with')),
    (10, 'agent inference',
     ('assumed', 'assumption', 'i believe', 'presumably', 'should exist',
      'expect it to', 'inferred', 'likely')),
]

WEAK_TIER_FLOOR = 8  # tiers >= this cannot support OBSERVED

# Security-sensitive subject matter. A defect here escalates in severity, and
# an UNVERIFIED status here blocks rather than warns.
SECURITY_KEYWORDS = (
    'auth', 'authn', 'authz', 'authentication', 'authorisation', 'authorization',
    'identity', 'privilege', 'permission', 'rbac', 'role', 'rank hierarchy',
    'tenant', 'jurisdiction', 'isolation', 'audit', 'audit log', 'input validation',
    'sanitis', 'sanitiz', 'escap', 'xss', 'csrf', 'injection', 'sql injection',
    'credential', 'secret', 'token', 'password', 'session', 'cookie',
    'encryption', 'crypto', 'pii', 'sensitive data', 'regulated',
    'payment', 'financial', 'transaction', 'billing',
    'delete', 'destructive', 'drop table', 'truncate', 'purge',
)

# Aggregate score patterns. Any of these invalidate the block.
AGGREGATE_PATTERNS = (
    re.compile(r'\b\d+\s*/\s*\d+\s*(?:items?\s*)?(?:passing|passed|pass)\b', re.I),
    re.compile(r'\b(?:overall|aggregate|total|combined)\s*(?:score|pass\s*rate|result)\b', re.I),
    re.compile(r'\b\d{1,3}\s*%\s*(?:passing|passed|pass|complete|compliant)\b', re.I),
    re.compile(r'\bpass\s*rate\s*[:=]', re.I),
    re.compile(r'\bscore\s*[:=]\s*\d+\s*/\s*\d+', re.I),
)

# Literal secret material. Matches an assignment to a plausible secret name
# followed by a value of meaningful length.
SECRET_PATTERNS = (
    re.compile(
        r'\b([A-Za-z_][A-Za-z0-9_]*(?:secret|token|password|passwd|api[_-]?key|'
        r'access[_-]?key|private[_-]?key|client[_-]?secret)[A-Za-z0-9_]*)\s*'
        r'[:=]\s*["\']?([A-Za-z0-9_\-./+=]{8,})["\']?',
        re.I,
    ),
    re.compile(r'\b(sk-[A-Za-z0-9]{16,})\b'),
    re.compile(r'\b(ghp_[A-Za-z0-9]{20,})\b'),
    re.compile(r'\b(AKIA[0-9A-Z]{12,})\b'),
    re.compile(r'\b(eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})\b'),
    re.compile(r'(mongodb(?:\+srv)?://[^\s"\'<>]*:[^\s"\'<>]+@[^\s"\'<>]+)', re.I),
    re.compile(r'(postgres(?:ql)?://[^\s"\'<>]*:[^\s"\'<>]+@[^\s"\'<>]+)', re.I),
)

SEVERITY_ORDER = ['Informational', 'Low', 'Medium', 'High', 'Critical']


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class ItemResult:
    """One checklist item after parsing and rule application."""

    number: Optional[int]
    check: str
    reported_status: str
    effective_status: str
    evidence: str = ''
    evidence_tier: Optional[int] = None
    evidence_tier_label: str = ''
    severity: str = ''
    confidence: str = ''
    security_sensitive: bool = False
    findings: list[str] = field(default_factory=list)
    blocking: bool = False


@dataclass
class GateReport:
    """Full gate outcome. Carries no aggregate score by design."""

    decision: str
    block_format: str
    source: str
    items: list[ItemResult] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    redactions: list[str] = field(default_factory=list)
    limitations: str = ''
    stack_profile: str = ''
    parse_errors: list[str] = field(default_factory=list)
    premise_findings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------

def redact(text: str) -> tuple[str, list[str]]:
    """Strip literal secret values, returning cleaned text and a description
    of what was removed. Location and type only — never the value itself."""
    redactions: list[str] = []
    cleaned = text
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(cleaned):
            groups = match.groups()
            label = groups[0] if len(groups) > 1 else 'credential material'
            value = groups[-1]
            if not value:
                continue
            redactions.append(f'{label} [REDACTED]')
            cleaned = cleaned.replace(value, '[REDACTED]')
    return cleaned, redactions


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def classify_evidence(evidence: str) -> tuple[Optional[int], str]:
    """Return the strongest evidence tier the text supports.

    Strongest wins: text citing both a passing test run and a naming convention
    is tier 2, because the stronger evidence is genuinely present.
    """
    if not evidence or not evidence.strip():
        return None, ''
    lowered = evidence.lower()
    for tier, label, markers in EVIDENCE_TIERS:
        if any(marker in lowered for marker in markers):
            return tier, label
    return None, ''


def is_security_sensitive(*texts: str) -> bool:
    haystack = ' '.join(t.lower() for t in texts if t)
    return any(keyword in haystack for keyword in SECURITY_KEYWORDS)


def normalise_status(raw: str) -> str:
    token = re.sub(r'[^A-Za-z]', '', (raw or '')).upper()
    for status in ALL_STATUSES:
        if token == status:
            return status
    # tolerate "PASSED"/"FAILED"
    if token.startswith('PASS'):
        return 'PASS'
    if token.startswith('FAIL'):
        return 'FAIL'
    return ''


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

TABLE_ROW = re.compile(r'^\s*\|(.+)\|\s*$')
PLAIN_ITEM = re.compile(
    r'^\s*(?:(\d+)[.)]\s*)?\*{0,2}(.+?)\*{0,2}\s*[—\-–:]\s*\[?\s*'
    r'(PASS|FAIL|OBSERVED|INFERRED|CLAIMED|UNVERIFIED|CONTRADICTED)\s*\]?\s*[:.]?\s*(.*)$',
    re.I,
)


def _split_row(line: str) -> list[str]:
    inner = TABLE_ROW.match(line)
    if not inner:
        return []
    return [cell.strip() for cell in inner.group(1).split('|')]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r':?-{2,}:?', c or '') for c in cells if c != '')


def parse_table(text: str) -> tuple[list[dict], list[str]]:
    """Parse the evidence-model table form."""
    rows: list[dict] = []
    errors: list[str] = []
    header: list[str] = []

    for line in text.splitlines():
        cells = _split_row(line)
        if not cells:
            continue
        if _is_separator_row(cells):
            continue
        lowered = [c.lower() for c in cells]
        if not header and any('check' in c for c in lowered) and any('status' in c for c in lowered):
            header = lowered
            continue
        if not header:
            continue

        record: dict = {}
        for idx, cell in enumerate(cells):
            key = header[idx] if idx < len(header) else f'col{idx}'
            record[key] = cell
        rows.append(record)

    if header and not rows:
        errors.append('verification table has a header but no item rows')
    return rows, errors


def parse_plain(text: str) -> list[dict]:
    """Parse the numbered PASS/FAIL checklist form."""
    rows: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('|') or stripped.startswith('>'):
            continue
        match = PLAIN_ITEM.match(stripped)
        if not match:
            continue
        number, check, status, remainder = match.groups()
        check_clean = check.strip().strip('*').strip()
        # Skip prose lines that merely mention a status word
        if len(check_clean) > 160:
            continue
        rows.append({
            '#': number or '',
            'check': check_clean,
            'status': status.upper(),
            'evidence': (remainder or '').strip(),
        })
    return rows


def _cell(record: dict, *candidates: str) -> str:
    for key, value in record.items():
        for candidate in candidates:
            if candidate in key:
                return value or ''
    return ''


def detect_format(text: str) -> str:
    table_rows, _ = parse_table(text)
    if table_rows:
        return 'evidence'
    if parse_plain(text):
        return 'plain'
    return 'unknown'


# --------------------------------------------------------------------------
# Rule application
# --------------------------------------------------------------------------

def evaluate_item(record: dict, extra_security_paths: tuple[str, ...]) -> ItemResult:
    number_raw = _cell(record, '#', 'num')
    try:
        number = int(re.sub(r'\D', '', number_raw)) if number_raw.strip() else None
    except ValueError:
        number = None

    check = _cell(record, 'check', 'item').strip()
    reported = normalise_status(_cell(record, 'status', 'result'))
    evidence_raw = _cell(record, 'evidence', 'basis')
    severity = _cell(record, 'severity').strip()
    confidence = _cell(record, 'confidence').strip()

    evidence, redactions = redact(evidence_raw)
    tier, tier_label = classify_evidence(evidence)

    security = is_security_sensitive(check, evidence, severity)
    if not security and extra_security_paths:
        security = is_security_sensitive(*extra_security_paths) and bool(
            any(p.lower() in (check + ' ' + evidence).lower() for p in extra_security_paths)
        )

    item = ItemResult(
        number=number,
        check=check,
        reported_status=reported or '(unparsed)',
        effective_status=reported or '(unparsed)',
        evidence=evidence,
        evidence_tier=tier,
        evidence_tier_label=tier_label,
        severity=severity,
        confidence=confidence,
        security_sensitive=security,
    )

    if redactions:
        item.findings.append('secret material redacted from evidence')

    if not reported:
        item.findings.append('status could not be parsed')
        item.blocking = True
        return item

    # Rule 3 — status inflation
    if reported == OBSERVED and tier is not None and tier >= WEAK_TIER_FLOOR:
        item.effective_status = CLAIMED
        item.findings.append(
            f'status inflation: OBSERVED asserted on tier-{tier} evidence '
            f'({tier_label}); downgraded to CLAIMED'
        )
        if security:
            item.blocking = True

    if reported == OBSERVED and tier is None and not evidence.strip():
        item.effective_status = CLAIMED
        item.findings.append('OBSERVED reported with no evidence stated; downgraded to CLAIMED')
        if security:
            item.blocking = True

    # Rule 1 — CONTRADICTED always blocks
    if reported == CONTRADICTED:
        item.findings.append('CONTRADICTED — code differs materially from what was stated')
        item.blocking = True

    # Plain-template FAIL blocks
    if reported == 'FAIL':
        item.findings.append('FAIL reported')
        item.blocking = True

    # Rule 2 — UNVERIFIED on a security path blocks; elsewhere it is acceptable
    if reported == UNVERIFIED:
        if security:
            item.findings.append('UNVERIFIED on a security-sensitive item')
            item.blocking = True
        else:
            item.findings.append('UNVERIFIED — acceptable, reason should be stated')
            if not evidence.strip():
                item.findings.append('no reason given for UNVERIFIED')

    # Security escalation on severity
    if security and severity:
        if severity.strip().capitalize() in ('Low', 'Medium', 'Informational'):
            item.findings.append(
                f'security escalation: severity {severity} understated for a '
                'security-boundary item'
            )

    return item


def check_aggregates(text: str) -> list[str]:
    found = []
    for pattern in AGGREGATE_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(match.group(0).strip())
    return found


def extract_limitations(text: str) -> str:
    match = re.search(
        r'(?im)^\s*(?:\*{0,2}|#{1,6}\s*)limitations?\*{0,2}\s*[:\-—]?\s*(.*?)(?:\n\s*\n|\Z)',
        text,
        re.S,
    )
    if not match:
        return ''
    return ' '.join(match.group(1).split())[:600]



# --------------------------------------------------------------------------
# Premise cross-check
# --------------------------------------------------------------------------

def check_premises(items: list[ItemResult], premises: list[dict]) -> tuple[list[str], bool]:
    """Flag verification items that rest on an unvalidated project premise.

    The gate checks what an agent claims about code. This checks the ground
    beneath it. An item can be entirely correct about the code and still be
    worthless because the premise it was built on was never validated — and
    nothing in a diff reveals that, because nothing in the diff is wrong.

    Matching is term overlap between the premise and the item's check and
    evidence text. Two or more distinctive shared terms is treated as a
    reference; one is too easily coincidental.

    Returns (findings, blocking).
    """
    findings: list[str] = []
    blocking = False

    for premise in premises:
        terms = {t.lower() for t in premise.get('terms', [])}
        if not terms:
            continue
        for item in items:
            haystack = f'{item.check} {item.evidence}'.lower()
            matched = {term for term in terms if term in haystack}
            if len(matched) < 2:
                continue
            label = f'item {item.number or "?"}'
            high_impact = bool(premise.get('high_impact'))
            findings.append(
                f'{label} rests on {premise["id"]} ({premise["title"]}), an OPEN '
                f'premise' + (' on a high-impact subject' if high_impact else '') +
                ' — validate the premise before relying on this item'
            )
            if high_impact:
                item.blocking = True
                item.findings.append(
                    f'built on unvalidated high-impact premise {premise["id"]}'
                )
                blocking = True

    return findings, blocking


# --------------------------------------------------------------------------
# Gate
# --------------------------------------------------------------------------

def run_gate(
    text: str,
    source: str = '<stdin>',
    stack_profile: str = '',
    security_paths: Optional[list[str]] = None,
    min_items: int = 0,
    premises: Optional[list[dict]] = None,
) -> GateReport:
    """Apply all gate rules to a verification block."""
    extra_paths = tuple(security_paths or ())
    block_format = detect_format(text)

    report = GateReport(
        decision=APPROVE,
        block_format=block_format,
        source=source,
        stack_profile=stack_profile,
    )

    if block_format == 'unknown':
        report.decision = BLOCK
        report.parse_errors.append(
            'no verification block found — expected either a PASS/FAIL checklist '
            'or an evidence table with Check and Status columns'
        )
        report.blocking_reasons.append('verification block missing or unparseable')
        return report

    if block_format == 'evidence':
        records, errors = parse_table(text)
        report.parse_errors.extend(errors)
    else:
        records = parse_plain(text)

    report.items = [evaluate_item(r, extra_paths) for r in records]

    # Rule 5 — redaction accounting
    _, doc_redactions = redact(text)
    report.redactions = sorted(set(doc_redactions))
    if report.redactions:
        report.warnings.append(
            'secret material was present in the verification block and has been '
            'redacted; treat any committed value as compromised'
        )

    # Rule 4 — aggregate scores invalidate the block
    aggregates = check_aggregates(text)
    if aggregates:
        report.decision = BLOCK
        for found in aggregates:
            report.blocking_reasons.append(
                f'aggregate pass score present ({found!r}); per-item status is required — '
                'averaging lets a critical failure hide behind cosmetic successes'
            )

    # Rule 6 — completeness
    if not report.items:
        report.decision = BLOCK
        report.blocking_reasons.append('verification block contains no parseable items')
    elif min_items and len(report.items) < min_items:
        report.decision = BLOCK
        report.blocking_reasons.append(
            f'verification block has {len(report.items)} items; '
            f'the profile requires at least {min_items}'
        )

    report.limitations = extract_limitations(text)
    if block_format == 'evidence' and not report.limitations:
        report.warnings.append(
            'no limitations statement — confidence ratings are not interpretable '
            'without one, and its absence is itself a warning sign'
        )

    if premises and report.items:
        premise_findings, premise_blocking = check_premises(report.items, premises)
        report.premise_findings = premise_findings
        if premise_blocking:
            report.decision = BLOCK
            report.blocking_reasons.append(
                'one or more items rest on an unvalidated high-impact premise'
            )
        elif premise_findings:
            report.warnings.extend(premise_findings)

    for item in report.items:
        if item.blocking:
            report.decision = BLOCK
            label = f'item {item.number}' if item.number else f'item "{item.check[:48]}"'
            reason = item.findings[0] if item.findings else item.effective_status
            report.blocking_reasons.append(f'{label}: {reason}')
        else:
            for finding in item.findings:
                report.warnings.append(
                    f'item {item.number or "?"}: {finding}'
                )

    return report


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_text(report: GateReport) -> str:
    lines = []
    lines.append('Verification Gate')
    lines.append('=' * 68)
    lines.append(f'Source   : {report.source}')
    lines.append(f'Format   : {report.block_format}')
    if report.stack_profile:
        lines.append(f'Profile  : {report.stack_profile}')
    lines.append(f'Decision : {report.decision.upper()}')
    lines.append('')

    if report.items:
        lines.append('Per-item results (no aggregate score by design):')
        for item in report.items:
            marker = 'BLOCK' if item.blocking else '  ok '
            status = item.effective_status
            if status != item.reported_status:
                status = f'{item.reported_status} -> {status}'
            sec = ' [security]' if item.security_sensitive else ''
            lines.append(f'  [{marker}] {item.number or "-"}. {item.check[:56]}{sec}')
            lines.append(f'           status: {status}')
            if item.evidence_tier:
                lines.append(
                    f'           evidence: tier {item.evidence_tier} '
                    f'({item.evidence_tier_label})'
                )
            if item.severity or item.confidence:
                lines.append(
                    f'           severity: {item.severity or "-"} | '
                    f'confidence: {item.confidence or "-"}'
                )
            for finding in item.findings:
                lines.append(f'           - {finding}')
        lines.append('')

    if report.blocking_reasons:
        lines.append('BLOCKING:')
        for reason in report.blocking_reasons:
            lines.append(f'  - {reason}')
        lines.append('')

    if report.warnings:
        lines.append('Warnings:')
        for warning in report.warnings:
            lines.append(f'  - {warning}')
        lines.append('')

    if report.redactions:
        lines.append('Redactions (location and type only):')
        for redaction in report.redactions:
            lines.append(f'  - {redaction}')
        lines.append('')

    if report.premise_findings:
        lines.append('Premise findings:')
        for finding in report.premise_findings:
            lines.append(f'  - {finding}')
        lines.append('')

    if report.limitations:
        lines.append(f'Limitations: {report.limitations}')
    if report.parse_errors:
        lines.append('Parse errors:')
        for err in report.parse_errors:
            lines.append(f'  - {err}')

    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Parse and enforce an agent pre-output verification block.',
    )
    parser.add_argument(
        'block',
        nargs='?',
        help='File containing the verification block (omit or use - to read stdin)',
    )
    parser.add_argument('--stack', default='', help='Stack profile name, for reporting')
    parser.add_argument(
        '--security-path',
        action='append',
        default=[],
        dest='security_paths',
        help='Additional path or term to treat as security-sensitive (repeatable)',
    )
    parser.add_argument(
        '--min-items',
        type=int,
        default=0,
        help='Minimum item count the block must contain',
    )
    parser.add_argument(
        '--ground-file',
        help=(
            'Path to a ground.index.json, or "auto" to derive it from the project. '
            'OPEN premises are cross-checked against the block.'
        ),
    )
    parser.add_argument(
        '--project-root',
        default='.',
        help='Project root, used with --ground-file auto',
    )
    parser.add_argument('--json', action='store_true', help='Emit JSON instead of text')
    args = parser.parse_args()

    if not args.block or args.block == '-':
        text = sys.stdin.read()
        source = '<stdin>'
    else:
        path = Path(args.block)
        if not path.is_file():
            print(f'error: no such file: {path}', file=sys.stderr)
            sys.exit(3)
        text = path.read_text(encoding='utf-8', errors='replace')
        source = str(path)

    premises = None
    if args.ground_file:
        try:
            import ground_file as gf
            if args.ground_file == 'auto':
                ground = gf.load(gf.project_id(args.project_root))
            else:
                path = Path(args.ground_file)
                data = json.loads(path.read_text(encoding='utf-8'))
                ground = gf.GroundFile(
                    project_id=data.get('project_id', ''),
                    updated=data.get('updated', ''),
                    assumptions=[
                        gf.Assumption(**{
                            k: rec.get(k, '') for k in
                            ('id', 'title', 'assumption', 'type', 'tier',
                             'evidence', 'created', 'last_validated')
                        })
                        for rec in data.get('assumptions', [])
                    ],
                )
            premises = gf.open_premises(ground)
        except Exception as exc:
            # A ground file that cannot be read is reported, not silently skipped:
            # silently skipping would turn a configuration error into an
            # unexplained pass.
            print(f'error: could not read ground file: {exc}', file=sys.stderr)
            sys.exit(3)

    report = run_gate(
        text,
        source=source,
        stack_profile=args.stack,
        security_paths=args.security_paths,
        min_items=args.min_items,
        premises=premises,
    )

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(render_text(report))

    if report.parse_errors and report.decision == BLOCK and not report.items:
        sys.exit(3)
    if report.decision == BLOCK:
        sys.exit(1)
    if report.warnings:
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    from _cli import guard_broken_pipe
    guard_broken_pipe(main)
