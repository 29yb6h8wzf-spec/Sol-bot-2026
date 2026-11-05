"""Paper profits are allowed only with proof; Demo cap remains immutable."""
import json
from decimal import Decimal as D

from portfolio_risk import approve
from futures_engine.paper import PaperLedger
from futures_engine.__main__ import approve_paper_portfolio_entry


def ledger_set(tmp_path):
    result = {}
    for coin in ('btc','eth','sol','xrp'):
        result[coin] = PaperLedger(tmp_path / f'paper-ledger-{coin}.json',D('37.50'))
        result[coin].roll_day(300000)
    return result


def profitable_ledger_set(tmp_path):
    result = ledger_set(tmp_path)
    s=result['sol']
    s.open_position({'side':'long','entry':'100','stop':'98','target':'104',
                     'quantity':'0.16','max_estimated_loss':'0.36',
                     'margin_estimate':'8'},300000)
    event=s.evaluate_exit([[1200000,100,105,99,104,10]],
                          D('0.0006'),D('0.0005'))
    assert event['reason']=='target'
    return result


def request(root, risk='0.10', notional='10', leverage=2):
    return approve_paper_portfolio_entry(
        {'entry':notional,'max_estimated_loss':risk},
        D('1'),leverage,root)


def test_default_guard_rejects_unproven_account_growth():
    assert approve(D('150.01'),D('150'),0,10,D('0.1')) == (False,'invalid_account')


def test_verified_paper_win_is_eligible_for_new_paper_entry(tmp_path):
    profitable_ledger_set(tmp_path)
    assert request(tmp_path) == (True,'approved_offline_only')


def test_after_verified_gain_per_trade_risk_cap_remains(tmp_path):
    profitable_ledger_set(tmp_path)
    assert request(tmp_path,risk='1.50001') == (False,'per_trade_risk')


def test_after_verified_gain_leverage_cap_remains(tmp_path):
    profitable_ledger_set(tmp_path)
    assert request(tmp_path,leverage=3) == (False,'invalid_account')


def test_after_verified_gain_daily_loss_cap_remains(tmp_path):
    profitable_ledger_set(tmp_path)
    # Today started above 150, then the portfolio sustained a 5% loss.
    assert approve(D('143.0'),D('150.5'),0,10,D('0.1'),
                   account_cap=D('151')) == (False,'daily_loss_limit')


def test_forged_paper_balance_is_rejected(tmp_path):
    profitable_ledger_set(tmp_path)
    path=tmp_path/'paper-ledger-btc.json'
    state=json.loads(path.read_text())
    state['equity']='100'
    path.write_text(json.dumps(state))
    assert request(tmp_path) == (False,'portfolio_state_unavailable')


def test_forged_paper_exit_pnl_is_rejected(tmp_path):
    profitable_ledger_set(tmp_path)
    path=tmp_path/'paper-ledger-sol.json'
    state=json.loads(path.read_text())
    state['history'][-1]['pnl']='100'
    state['equity']='137.50'
    path.write_text(json.dumps(state))
    assert request(tmp_path) == (False,'portfolio_state_unavailable')


def test_missing_history_above_initial_cap_is_rejected(tmp_path):
    profitable_ledger_set(tmp_path)
    path=tmp_path/'paper-ledger-btc.json'
    state=json.loads(path.read_text())
    state.pop('history')
    path.write_text(json.dumps(state))
    assert request(tmp_path) == (False,'portfolio_state_unavailable')


def test_no_profit_keeps_original_small_account_behavior(tmp_path):
    ledger_set(tmp_path)
    assert request(tmp_path) == (True,'approved_offline_only')
