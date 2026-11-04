from portfolio_risk import approve
def test_accept_small(): assert approve(150,150,0,50,1.5)==(True,'approved_offline_only')
def test_shared_margin(): assert approve(150,150,125,60,1)[0] is False
def test_daily_limit(): assert approve(142.5,150,0,10,0.1)[0] is False
def test_trade_limit(): assert approve(150,150,0,10,1.51)[0] is False
def test_open_risk(): assert approve(150,150,0,10,1.5,open_risk=6.5)[0] is False
def test_bad_inputs(): assert approve(150,150,-1,10,1)[0] is False
