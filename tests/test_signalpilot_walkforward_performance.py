from signalpilot_walkforward import evaluate

def bars(n,step,base):return [[base+i*step,100,101,99,100,1000] for i in range(n)]

def test_cached_thresholds_match_individual_replay():
    f=bars(260,300000,14400000*200);h=bars(260,14400000,0)
    both=evaluate(f,h,thresholds=(70,85))
    for threshold in (70,85):
        solo=evaluate(f,h,thresholds=(threshold,))
        assert both["thresholds"][str(threshold)]==solo["thresholds"][str(threshold)]
    assert both["orders_sent"] is False
