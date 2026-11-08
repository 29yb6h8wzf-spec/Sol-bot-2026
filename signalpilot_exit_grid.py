"""Research-only parameter grid. Uses chronological training selection and untouched holdout.
No orders, no secrets, no changes to live strategy. Requires preloaded candles.
"""
from signalpilot_walkforward import evaluate

CANDIDATES=(
    {"strategy":"EMA_ADX","threshold":70,"stop_atr":"1","target_atr":"1.5","hold":3},
    {"strategy":"EMA_ADX","threshold":85,"stop_atr":"1.5","target_atr":"2","hold":12},
    {"strategy":"RSI_BOLL","threshold":70,"stop_atr":"1","target_atr":"1","hold":3},
    {"strategy":"RSI_BOLL","threshold":75,"stop_atr":"1.5","target_atr":"2","hold":12},
    {"strategy":"MACD_VOLUME","threshold":70,"stop_atr":"1","target_atr":"1","hold":3},
    {"strategy":"MACD_VOLUME","threshold":85,"stop_atr":"1.5","target_atr":"2","hold":12},
)

def _summary(result, threshold):
    data=result["thresholds"][str(threshold)]
    n=data["trades"]
    return {"trades":n,"wins":data["wins"],"mean_net_pct":data["sum_net_return_pct_uncompounded"]/n if n else None,
            "sum_net_pct_uncompounded":data["sum_net_return_pct_uncompounded"]}

def run(five,four,*,candidates=CANDIDATES,min_train_trades=30):
    if not isinstance(five,list) or len(five)<1000:raise ValueError("insufficient_5m_history")
    split=len(five)*7//10
    boundary=five[split][0]
    training=[]
    for params in candidates:
        if params["strategy"] not in ("EMA_ADX","RSI_BOLL","MACD_VOLUME"):raise ValueError("invalid_strategy")
        args=dict(thresholds=(params["threshold"],),allowed_strategies=(params["strategy"],),
                  stop_atr=params["stop_atr"],target_atr=params["target_atr"],max_holding_bars=params["hold"])
        result=evaluate(five,four,max_exit_ms=boundary,**args)
        stats=_summary(result,params["threshold"])
        training.append({"params":params,"stats":stats})
    qualified=[x for x in training if x["stats"]["trades"]>=min_train_trades]
    # Select using TRAIN only; holdout must not influence choice.
    winner=max(qualified,key=lambda x:x["stats"]["mean_net_pct"]) if qualified else None
    holdout=None
    if winner:
        p=winner["params"]
        result=evaluate(five,four,min_signal_ms=boundary,thresholds=(p["threshold"],),
                        allowed_strategies=(p["strategy"],),stop_atr=p["stop_atr"],
                        target_atr=p["target_atr"],max_holding_bars=p["hold"])
        holdout=_summary(result,p["threshold"])
    return {"status":"OFFLINE_RESEARCH_ONLY","orders_sent":False,"split_ms":boundary,
            "min_train_trades":min_train_trades,"training":training,"selected_train_only":winner,"holdout":holdout,
            "funding_included":False,"position_sizing_included":False}
