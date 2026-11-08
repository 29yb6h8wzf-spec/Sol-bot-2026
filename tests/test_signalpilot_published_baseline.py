import pytest
from signalpilot_published_baseline import evaluate

def market(n=80):
 return {s:[[i*300000,100+i*(k+1)*0.1,102+i*(k+1)*0.1,99+i*(k+1)*0.1,100+i*(k+1)*0.1,1000] for i in range(n)] for k,s in enumerate(("BTC","ETH","SOL","XRP"))}

def test_baseline_no_orders_and_aligned_trades():
 result=evaluate(market(),lookback=5,holding=3)
 assert result["orders_sent"] is False and result["paper_exact_replication"] is False
 assert result["trades"]>0
 assert all(t["exit_ms"]>t["signal_ms"] for t in result["trade_log"])

def test_misaligned_data_fail_closed():
 m=market();m["XRP"][10][0]+=300000
 with pytest.raises(ValueError,match="gapped_history"):evaluate(m)

def test_negative_costs_fail_closed():
 with pytest.raises(ValueError,match="invalid_costs"):evaluate(market(),fee_per_side="-0.1")
