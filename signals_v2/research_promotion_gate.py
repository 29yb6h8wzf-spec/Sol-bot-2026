"""Fail-closed research promotion gate. Never authorizes live trading."""
import json,sys
from pathlib import Path

def assess(report):
    if report.get("months_received")!=24 or report.get("oos_certified") is not False:
        return {"eligible":False,"reason":"incomplete_or_unverified_research"}
    symbols=report.get("symbols",{})
    if set(symbols)!={"SOLUSDT","XRPUSDT"}:
        return {"eligible":False,"reason":"missing_symbol"}
    for symbol,data in symbols.items():
        if data.get("trades",0)<200:
            return {"eligible":False,"reason":f"insufficient_trades:{symbol}"}
        if data.get("weighted_mean_net_r") is None or data["weighted_mean_net_r"]<=0:
            return {"eligible":False,"reason":f"nonpositive_net_expectancy:{symbol}"}
    return {"eligible":False,"reason":"oos_validation_required_even_if_exploratory_positive"}

if __name__=="__main__":
    report=json.loads(Path(sys.argv[1]).read_text())
    result=assess(report)
    print(json.dumps(result,indent=2))
    if result["eligible"]:raise SystemExit("unexpected_promotion")
