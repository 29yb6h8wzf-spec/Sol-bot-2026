import pytest
from signalpilot_walkforward import evaluate

def bars(n,step,base):return [[base+i*step,100,101,99,100,1000] for i in range(n)]

def test_optional_quality_gates_research_only():
 f=bars(250,300000,14400000*200);h=bars(250,14400000,0)
 r=evaluate(f,h,min_volume_ratio="2",min_atr_pct="0.5")
 assert r["orders_sent"] is False
 assert r["min_volume_ratio"]=="2" and r["min_atr_pct"]=="0.5"
 assert r["quality_rejected_bars"]>=0

def test_negative_quality_gate_rejected():
 with pytest.raises(ValueError,match="invalid_min_atr_pct"):
  evaluate(bars(250,300000,14400000*200),bars(250,14400000,0),min_atr_pct="-1")
