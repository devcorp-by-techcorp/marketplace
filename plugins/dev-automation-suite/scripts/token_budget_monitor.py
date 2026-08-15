#!/usr/bin/env python3
"""
Token Budget Monitor — tracks and enforces token usage across the
automate-dev workflow.

Initialises token budgets per phase, records usage as phases execute,
and enforces limits to prevent runaway costs during agentic loops.
Optimised for Claude Opus 4.7 with its 1.0-1.35x token multiplier
over Opus 4.6.

Usage:
    python token_budget_monitor.py init <project_root> [--total-budget N] [--difficulty LEVEL]
    python token_budget_monitor.py check <project_root> --phase NAME [--requested N]
    python token_budget_monitor.py record <project_root> --phase NAME --tokens N [--model MODEL]
    python token_budget_monitor.py summary <project_root>
    python token_budget_monitor.py report <project_root>
    python token_budget_monitor.py reset <project_root>
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# Opus 4.7 pricing: $5/$25 per MTok input/output
# Sonnet 4.6 pricing: $3/$15 per MTok input/output
MODEL_PRICING = {
    'claude-opus-4-7': {'input': 5.0, 'output': 25.0},
    'claude-opus-4-6': {'input': 5.0, 'output': 25.0},
    'opus': {'input': 5.0, 'output': 25.0},
    'claude-sonnet-4-6': {'input': 3.0, 'output': 15.0},
    'sonnet': {'input': 3.0, 'output': 15.0},
    'claude-haiku-4-5': {'input': 1.0, 'output': 5.0},
    'haiku': {'input': 1.0, 'output': 5.0},
}


# Default phase budgets (input + output combined)
DEFAULT_PHASE_BUDGETS = {
    'analyse': 80_000,
    'build': 150_000,
    'review': 120_000,
    'test': 40_000,
    'fix': 60_000,
    'simplify': 40_000,
    'validate': 80_000,
    'ship': 20_000,
}


# Difficulty multipliers applied to default budgets
DIFFICULTY_MULTIPLIERS = {
    'low': 0.5,
    'medium': 1.0,
    'high': 1.5,
    'xhigh': 2.0,
    'max': 3.0,
}


# Alert thresholds as percentage of budget
ALERT_THRESHOLDS = {
    'warning_50': 0.50,
    'warning_75': 0.75,
    'halt_parallel_90': 0.90,
    'escalate_100': 1.00,
}


@dataclass
class PhaseUsage:
    """Token usage for a single phase."""
    phase: str
    budget: int
    tokens_used: int = 0
    invocations: int = 0
    by_model: dict = field(default_factory=dict)


@dataclass
class BudgetState:
    """Complete budget tracking state."""
    project_root: str
    total_budget: int
    total_used: int
    difficulty: str
    phases: dict
    iteration: int
    created_at: str
    updated_at: str
    status: str
    alerts: list = field(default_factory=list)


def get_state_dir(project_root: str) -> Path:
    """Get or create the .automate-dev directory."""
    state_dir = Path(project_root) / '.automate-dev'
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_budget_path(project_root: str) -> Path:
    """Get the path to the budget tracking file."""
    return get_state_dir(project_root) / 'token_budget.json'


def load_state(project_root: str) -> Optional[BudgetState]:
    """Load existing budget state."""
    budget_path = get_budget_path(project_root)
    if not budget_path.exists():
        return None
    try:
        with open(budget_path, 'r') as f:
            data = json.load(f)
        return BudgetState(**data)
    except (json.JSONDecodeError, TypeError) as e:
        print(f'Warning: could not load budget state: {e}', file=sys.stderr)
        return None


def save_state(state: BudgetState) -> None:
    """Persist budget state to disk."""
    state.updated_at = datetime.now().isoformat()
    budget_path = get_budget_path(state.project_root)
    with open(budget_path, 'w') as f:
        json.dump(asdict(state), f, indent=2)


def calculate_phase_budgets(total_budget: int, difficulty: str) -> dict:
    """Calculate per-phase budgets based on total and difficulty."""
    multiplier = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
    base_total = sum(DEFAULT_PHASE_BUDGETS.values())
    adjusted_budgets = {
        phase: int(budget * multiplier)
        for phase, budget in DEFAULT_PHASE_BUDGETS.items()
    }
    adjusted_total = sum(adjusted_budgets.values())

    # Scale proportionally if total_budget was specified
    if total_budget and total_budget != adjusted_total:
        scale = total_budget / adjusted_total
        adjusted_budgets = {
            phase: int(budget * scale)
            for phase, budget in adjusted_budgets.items()
        }

    return adjusted_budgets


def calculate_cost(tokens: int, model: str, io_type: str = 'mixed') -> float:
    """Calculate approximate USD cost for tokens on a given model."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING['claude-opus-4-7'])
    if io_type == 'input':
        return (tokens / 1_000_000) * pricing['input']
    if io_type == 'output':
        return (tokens / 1_000_000) * pricing['output']
    # Mixed: assume 70% input, 30% output as typical split
    input_cost = (tokens * 0.7 / 1_000_000) * pricing['input']
    output_cost = (tokens * 0.3 / 1_000_000) * pricing['output']
    return input_cost + output_cost


def determine_status(total_used: int, total_budget: int) -> str:
    """Determine current budget status."""
    if total_budget <= 0:
        return 'NO_BUDGET'
    pct = total_used / total_budget
    if pct >= ALERT_THRESHOLDS['escalate_100']:
        return 'OVER_BUDGET'
    if pct >= ALERT_THRESHOLDS['halt_parallel_90']:
        return 'CRITICAL'
    if pct >= ALERT_THRESHOLDS['warning_75']:
        return 'WARNING_75'
    if pct >= ALERT_THRESHOLDS['warning_50']:
        return 'WARNING_50'
    return 'ON_TRACK'


def check_phase_budget(
    state: BudgetState,
    phase: str,
    requested_tokens: int,
) -> dict:
    """Check if a phase can accommodate the requested token usage."""
    phase_data = state.phases.get(phase)
    if phase_data is None:
        return {
            'phase': phase,
            'approved': False,
            'reason': f'Unknown phase: {phase}',
        }

    budget = phase_data['budget']
    used = phase_data['tokens_used']
    available = budget - used
    total_available = state.total_budget - state.total_used

    # Check phase-level budget
    if requested_tokens > available:
        return {
            'phase': phase,
            'approved': False,
            'requested': requested_tokens,
            'phase_budget': budget,
            'phase_used': used,
            'phase_available': available,
            'reason': f'Phase budget would be exceeded: '
                      f'requesting {requested_tokens}, only {available} available',
        }

    # Check total budget
    if requested_tokens > total_available:
        return {
            'phase': phase,
            'approved': False,
            'requested': requested_tokens,
            'total_budget': state.total_budget,
            'total_used': state.total_used,
            'total_available': total_available,
            'reason': f'Total budget would be exceeded: '
                      f'requesting {requested_tokens}, only {total_available} available',
        }

    # Check critical threshold (90% total)
    projected_total = state.total_used + requested_tokens
    projected_pct = projected_total / state.total_budget if state.total_budget else 0

    warnings = []
    if projected_pct >= ALERT_THRESHOLDS['halt_parallel_90']:
        warnings.append(
            f'Will exceed 90% of total budget — halt parallel agent launches'
        )
    elif projected_pct >= ALERT_THRESHOLDS['warning_75']:
        warnings.append(
            f'Will exceed 75% of total budget — monitor closely'
        )

    return {
        'phase': phase,
        'approved': True,
        'requested': requested_tokens,
        'phase_budget': budget,
        'phase_used': used,
        'phase_available_after': available - requested_tokens,
        'total_used_after': projected_total,
        'total_budget': state.total_budget,
        'projected_pct': round(projected_pct * 100, 1),
        'warnings': warnings,
    }


def cmd_init(args: argparse.Namespace) -> None:
    """Initialise budget tracking for a project."""
    difficulty = args.difficulty or 'medium'
    if difficulty not in DIFFICULTY_MULTIPLIERS:
        print(json.dumps({
            'error': f'Invalid difficulty: {difficulty}. '
                     f'Must be one of: {list(DIFFICULTY_MULTIPLIERS.keys())}'
        }))
        sys.exit(1)

    if args.total_budget:
        total_budget = args.total_budget
        phase_budgets = calculate_phase_budgets(total_budget, difficulty)
    else:
        phase_budgets = calculate_phase_budgets(0, difficulty)
        total_budget = sum(phase_budgets.values())

    phases = {
        phase: asdict(PhaseUsage(phase=phase, budget=budget))
        for phase, budget in phase_budgets.items()
    }

    now = datetime.now().isoformat()
    state = BudgetState(
        project_root=args.project_root,
        total_budget=total_budget,
        total_used=0,
        difficulty=difficulty,
        phases=phases,
        iteration=0,
        created_at=now,
        updated_at=now,
        status='ON_TRACK',
    )
    save_state(state)

    print(json.dumps({
        'status': 'INITIALISED',
        'project_root': args.project_root,
        'total_budget': total_budget,
        'difficulty': difficulty,
        'phase_budgets': phase_budgets,
        'estimated_cost_usd': {
            'all_opus_4_7': round(calculate_cost(total_budget, 'claude-opus-4-7'), 2),
            'all_sonnet_4_6': round(calculate_cost(total_budget, 'claude-sonnet-4-6'), 2),
        },
    }, indent=2))


def cmd_check(args: argparse.Namespace) -> None:
    """Check if a phase can accommodate requested tokens."""
    state = load_state(args.project_root)
    if state is None:
        print(json.dumps({
            'error': 'No budget state found. Run init first.'
        }))
        sys.exit(1)

    requested = args.requested or 0
    result = check_phase_budget(state, args.phase, requested)
    print(json.dumps(result, indent=2))

    sys.exit(0 if result.get('approved') else 1)


def cmd_record(args: argparse.Namespace) -> None:
    """Record token usage for a phase."""
    state = load_state(args.project_root)
    if state is None:
        print(json.dumps({
            'error': 'No budget state found. Run init first.'
        }))
        sys.exit(1)

    phase_data = state.phases.get(args.phase)
    if phase_data is None:
        print(json.dumps({
            'error': f'Unknown phase: {args.phase}. '
                     f'Valid phases: {list(state.phases.keys())}'
        }))
        sys.exit(1)

    phase_data['tokens_used'] += args.tokens
    phase_data['invocations'] += 1

    model = args.model or 'claude-opus-4-7'
    by_model = phase_data.get('by_model', {})
    by_model[model] = by_model.get(model, 0) + args.tokens
    phase_data['by_model'] = by_model

    state.total_used += args.tokens
    state.status = determine_status(state.total_used, state.total_budget)

    # Record alerts
    pct = state.total_used / state.total_budget if state.total_budget else 0
    if state.status == 'OVER_BUDGET':
        state.alerts.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'OVER_BUDGET',
            'message': f'Total budget exceeded: {state.total_used}/{state.total_budget}',
        })
    elif state.status == 'CRITICAL':
        state.alerts.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'CRITICAL',
            'message': f'90% threshold reached — halt parallel launches',
        })

    save_state(state)

    phase_pct = (phase_data['tokens_used'] / phase_data['budget'] * 100
                 if phase_data['budget'] else 0)
    total_pct = (state.total_used / state.total_budget * 100
                 if state.total_budget else 0)

    print(json.dumps({
        'status': 'RECORDED',
        'phase': args.phase,
        'tokens_added': args.tokens,
        'model': model,
        'phase_used': phase_data['tokens_used'],
        'phase_budget': phase_data['budget'],
        'phase_pct': round(phase_pct, 1),
        'total_used': state.total_used,
        'total_budget': state.total_budget,
        'total_pct': round(total_pct, 1),
        'overall_status': state.status,
        'estimated_cost_usd': round(calculate_cost(args.tokens, model), 4),
    }, indent=2))

    sys.exit(2 if state.status in ('OVER_BUDGET', 'CRITICAL') else 0)


def cmd_summary(args: argparse.Namespace) -> None:
    """Show current budget usage summary."""
    state = load_state(args.project_root)
    if state is None:
        print(json.dumps({
            'error': 'No budget state found. Run init first.'
        }))
        sys.exit(1)

    pct = (state.total_used / state.total_budget * 100
           if state.total_budget else 0)

    summary = {
        'total_budget': state.total_budget,
        'total_used': state.total_used,
        'remaining': state.total_budget - state.total_used,
        'percentage_used': round(pct, 1),
        'status': state.status,
        'difficulty': state.difficulty,
        'iteration': state.iteration,
        'by_phase': {},
        'alert_count': len(state.alerts),
    }

    for phase_name, phase_data in state.phases.items():
        phase_pct = (phase_data['tokens_used'] / phase_data['budget'] * 100
                     if phase_data['budget'] else 0)
        summary['by_phase'][phase_name] = {
            'budget': phase_data['budget'],
            'used': phase_data['tokens_used'],
            'pct': round(phase_pct, 1),
            'invocations': phase_data['invocations'],
        }

    print(json.dumps(summary, indent=2))


def cmd_report(args: argparse.Namespace) -> None:
    """Generate detailed budget report."""
    state = load_state(args.project_root)
    if state is None:
        print(json.dumps({
            'error': 'No budget state found.'
        }))
        sys.exit(1)

    # Calculate costs by model
    total_cost = 0.0
    cost_by_model = {}
    for phase_data in state.phases.values():
        for model, tokens in phase_data.get('by_model', {}).items():
            cost = calculate_cost(tokens, model)
            cost_by_model[model] = cost_by_model.get(model, 0) + cost
            total_cost += cost

    pct = (state.total_used / state.total_budget * 100
           if state.total_budget else 0)

    report = {
        'project_root': state.project_root,
        'difficulty': state.difficulty,
        'status': state.status,
        'created_at': state.created_at,
        'updated_at': state.updated_at,
        'iteration': state.iteration,
        'totals': {
            'budget': state.total_budget,
            'used': state.total_used,
            'remaining': state.total_budget - state.total_used,
            'percentage_used': round(pct, 1),
            'estimated_total_cost_usd': round(total_cost, 2),
        },
        'by_phase': {},
        'by_model': {
            model: {
                'tokens': sum(
                    p.get('by_model', {}).get(model, 0)
                    for p in state.phases.values()
                ),
                'estimated_cost_usd': round(cost, 4),
            }
            for model, cost in cost_by_model.items()
        },
        'alerts': state.alerts,
    }

    for phase_name, phase_data in state.phases.items():
        phase_pct = (phase_data['tokens_used'] / phase_data['budget'] * 100
                     if phase_data['budget'] else 0)
        report['by_phase'][phase_name] = {
            'budget': phase_data['budget'],
            'used': phase_data['tokens_used'],
            'remaining': phase_data['budget'] - phase_data['tokens_used'],
            'percentage': round(phase_pct, 1),
            'invocations': phase_data['invocations'],
            'by_model': phase_data.get('by_model', {}),
        }

    print(json.dumps(report, indent=2))

    # Write markdown report
    report_path = get_state_dir(state.project_root) / 'token_budget_report.md'
    with open(report_path, 'w') as f:
        f.write('# Token Budget Report\n\n')
        f.write(f'**Project**: {state.project_root}\n')
        f.write(f'**Status**: {state.status}\n')
        f.write(f'**Difficulty**: {state.difficulty}\n')
        f.write(f'**Iteration**: {state.iteration}\n\n')
        f.write('## Totals\n')
        f.write(f'- Budget: {state.total_budget:,} tokens\n')
        f.write(f'- Used: {state.total_used:,} tokens ({pct:.1f}%)\n')
        f.write(f'- Remaining: {state.total_budget - state.total_used:,} tokens\n')
        f.write(f'- Estimated cost: ${total_cost:.2f} USD\n\n')
        f.write('## Phase Breakdown\n\n')
        f.write('| Phase | Budget | Used | % | Invocations |\n')
        f.write('|-------|--------|------|---|-------------|\n')
        for phase_name, phase_info in report['by_phase'].items():
            f.write(
                f'| {phase_name} | {phase_info["budget"]:,} | '
                f'{phase_info["used"]:,} | {phase_info["percentage"]:.1f}% | '
                f'{phase_info["invocations"]} |\n'
            )
        if state.alerts:
            f.write(f'\n## Alerts ({len(state.alerts)})\n\n')
            for alert in state.alerts:
                f.write(f'- [{alert["timestamp"]}] **{alert["type"]}**: {alert["message"]}\n')


def cmd_reset(args: argparse.Namespace) -> None:
    """Reset budget tracking for a project."""
    budget_path = get_budget_path(args.project_root)
    if budget_path.exists():
        budget_path.unlink()
    print(json.dumps({
        'status': 'RESET',
        'project_root': args.project_root,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description='Token Budget Monitor — tracks token usage across automate-dev workflow'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # init
    init_parser = subparsers.add_parser('init', help='Initialise budget tracking')
    init_parser.add_argument('project_root', help='Project root directory')
    init_parser.add_argument('--total-budget', type=int, help='Total token budget (default: calculated from phase defaults)')
    init_parser.add_argument('--difficulty', choices=list(DIFFICULTY_MULTIPLIERS.keys()),
                              help='Task difficulty (affects budget scaling)')

    # check
    check_parser = subparsers.add_parser('check', help='Check if a phase has budget for requested tokens')
    check_parser.add_argument('project_root', help='Project root directory')
    check_parser.add_argument('--phase', required=True, help='Phase name')
    check_parser.add_argument('--requested', type=int, help='Tokens being requested')

    # record
    record_parser = subparsers.add_parser('record', help='Record token usage')
    record_parser.add_argument('project_root', help='Project root directory')
    record_parser.add_argument('--phase', required=True, help='Phase name')
    record_parser.add_argument('--tokens', type=int, required=True, help='Tokens used')
    record_parser.add_argument('--model', help='Model used (affects cost calculation)')

    # summary
    summary_parser = subparsers.add_parser('summary', help='Show current usage summary')
    summary_parser.add_argument('project_root', help='Project root directory')

    # report
    report_parser = subparsers.add_parser('report', help='Generate detailed report')
    report_parser.add_argument('project_root', help='Project root directory')

    # reset
    reset_parser = subparsers.add_parser('reset', help='Reset budget tracking')
    reset_parser.add_argument('project_root', help='Project root directory')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        'init': cmd_init,
        'check': cmd_check,
        'record': cmd_record,
        'summary': cmd_summary,
        'report': cmd_report,
        'reset': cmd_reset,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
