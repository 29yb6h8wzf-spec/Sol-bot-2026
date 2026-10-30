"""Read-only, deterministic performance summary of a SignalPilot paper ledger.

No exchange connection, no authenticated API and no trading side effects.
Only closed paper exits count toward realized performance.
"""
from decimal import Decimal as D


def _money(value):
    result = D(str(value))
    if not result.is_finite():
        raise ValueError('nonfinite ledger amount')
    return result


def summarize_paper_ledger(state):
    if not isinstance(state, dict) or not isinstance(state.get('history'), list):
        raise ValueError('invalid paper ledger')
    equity = _money(state['equity'])
    day_start = _money(state['day_start_equity'])
    if equity <= 0 or day_start <= 0:
        raise ValueError('invalid paper equity')
    exits = [item for item in state['history'] if item.get('event') == 'paper_exit']
    pnl_values = [_money(item['pnl']) for item in exits]
    costs = [_money(item['costs']) for item in exits]
    if any(cost < 0 for cost in costs):
        raise ValueError('invalid paper costs')
    realized = sum(pnl_values, D(0))
    # Older ledgers did not record the original balance; their totals are estimates.
    verified = 'initial_equity' in state
    initial = _money(state['initial_equity']) if verified else equity - realized
    if initial <= 0:
        raise ValueError('invalid initial paper equity')
    wins = sum(p > 0 for p in pnl_values)
    losses = sum(p < 0 for p in pnl_values)
    breakeven = len(exits) - wins - losses
    gross_wins = sum((p for p in pnl_values if p > 0), D(0))
    gross_losses = -sum((p for p in pnl_values if p < 0), D(0))
    peak = initial
    balance = initial
    max_drawdown = D(0)
    consecutive_losses = 0
    max_consecutive_losses = 0
    for pnl in pnl_values:
        balance += pnl
        peak = max(peak, balance)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - balance) / peak * 100)
        consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0
        max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
    # Reconciliation is meaningful only when the initial balance was persisted.
    if verified and balance != equity:
        raise ValueError('paper ledger equity does not reconcile with exits')
    return {
        'mode': 'paper_only',
        'equity_reconciled': verified,
        'closed_trades': len(exits),
        'wins': wins,
        'losses': losses,
        'breakeven': breakeven,
        'win_rate_pct': str(D(wins) / D(len(exits)) * 100) if exits else None,
        'net_realized_pnl_usdt': str(realized),
        'modeled_costs_usdt': str(sum(costs, D(0))),
        'initial_equity_usdt': str(initial),
        'current_equity_usdt': str(equity),
        'max_closed_equity_drawdown_pct': str(max_drawdown),
        'max_consecutive_losses': max_consecutive_losses,
        'profit_factor': str(gross_wins / gross_losses) if gross_losses else None,
        'open_position': state.get('position') is not None,
        'day_start_equity_usdt': str(day_start),
        'unrealized_pnl_included': False,
    }


def main(argv=None):
    """Print a JSON report from an existing paper ledger without running a scan."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Read-only SignalPilot paper ledger report')
    parser.add_argument('ledger', nargs='?', default='paper-ledger.json',
                        help='Path to an existing paper ledger JSON file')
    args = parser.parse_args(argv)
    with Path(args.ledger).open(encoding='utf-8') as stream:
        state = json.load(stream)
    report = summarize_paper_ledger(state)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
