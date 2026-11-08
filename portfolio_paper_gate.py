from decimal import Decimal as D
from pathlib import Path
import json
import sys

base = Path('/opt/signalpilot')
try:
    states = [json.loads((base / f'paper-ledger-{coin}.json').read_text())
              for coin in ('sol', 'xrp')]
    equity = sum((D(state['equity']) for state in states), D('0'))
    day_start = sum((D(state['day_start_equity']) for state in states), D('0'))
    if not all(x.is_finite() and x > 0 for x in (equity, day_start)):
        raise ValueError('invalid_portfolio_balance')
    if day_start - equity >= D('7.50'):
        print(f'PORTFOLIO_PAPER_PAUSED daily_loss={day_start-equity}')
        sys.exit(1)
    print(f'PORTFOLIO_PAPER_OK equity={equity} daily_loss={day_start-equity}')
except Exception as exc:
    print(f'PORTFOLIO_PAPER_BLOCKED {type(exc).__name__}')
    sys.exit(1)
