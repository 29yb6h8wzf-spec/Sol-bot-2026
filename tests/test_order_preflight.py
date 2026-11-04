from futures_engine.order_preflight import check
ACCOUNT={'equity':150,'day_start':150,'used_margin':0,'open_risk':0,'leverage':2}
ORDER={'symbol':'SOL/USDT:USDT','side':'long','source':'verified_85_score_engine','score':90,'entry':100,'stop':99,'target':102,'quantity':1}
def test_good(): assert check(ORDER,ACCOUNT)==(True,'approved_offline_only')
def test_score(): assert check({**ORDER,'score':84},ACCOUNT)[0] is False
def test_source(): assert check({**ORDER,'source':'ema_crossover'},ACCOUNT)[0] is False
def test_stop(): assert check({**ORDER,'stop':101},ACCOUNT)[0] is False
def test_risk(): assert check({**ORDER,'quantity':2},ACCOUNT)[0] is False
def test_symbol(): assert check({**ORDER,'symbol':'DOGE/USDT:USDT'},ACCOUNT)[0] is False
def test_daily_loss(): assert check(ORDER,{**ACCOUNT,'equity':142.5})[0] is False
def test_short(): assert check({**ORDER,'side':'short','stop':101,'target':98},ACCOUNT)[0] is True
