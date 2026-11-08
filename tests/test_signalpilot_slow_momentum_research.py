from signalpilot_slow_momentum_research import evaluate

def test_no_orders():
 rows=[[i*300000,100+i*.1,101+i*.1,99+i*.1,100+i*.1,100] for i in range(100)]
 r=evaluate(rows,lookback_bars=10,hold_bars=12)
 assert r["orders_sent"] is False and r["trades"]>0
 assert all(t["exit_ms"]>t["signal_ms"] for t in r["trade_log"])

def test_insufficient_data_rejected():
 try:evaluate([[0,1,2,.5,1,1]])
 except ValueError:pass
 else:raise AssertionError("should fail closed")
