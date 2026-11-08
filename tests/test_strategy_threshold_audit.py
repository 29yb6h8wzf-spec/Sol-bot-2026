from strategy_threshold_audit import summarize
import pytest

def test_threshold_counts_are_not_success_rates():
    x=summarize([{"score":70,"strategy":"RSI_BOLL"},
                 {"score":79,"strategy":"EMA_ADX"},
                 {"score":85,"strategy":"MACD_VOLUME"}])
    assert x["counts_by_threshold"]=={"70":3,"75":2,"80":1,"85":1}
    assert x["win_rate_known"] is False and x["orders_sent"] is False

def test_bad_scores_fail_closed():
    for x in [None, [{"score":True}], [{"score":101}], [{"score":70.5}]]:
        with pytest.raises(ValueError): summarize(x)
