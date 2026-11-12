"""One-month research-only SOL/XRP replay pilot. Not an OOS profitability claim."""
import argparse,bisect,json
from collections import Counter
from pathlib import Path
from signals_v2.contracts import Candle,MarketSnapshot,DataRejected
from signals_v2.hybrid import candidates
from signals_v2.guarded_replay import guarded_replay
from signals_v2.backtest_exclusion_gate import load_manifest
from signals_v2.enumerate_all_mismatches import iter_rows

def candles(path,duration):
    out=[]
    for t,r in iter_rows(path):
        out.append(Candle(t,*(float(x) for x in r[1:6]),t+duration))
    return out

def run(root,manifest,month="2026-09",stride=12):
    intervals=load_manifest(manifest);report={"month":month,"stride_5m_bars":stride,"research_only":True,
      "out_of_sample_certified":False,"symbols":{}}
    for symbol in ("SOLUSDT","XRPUSDT"):
        five=candles(root/f"{symbol}-5m-{month}.zip",300000)
        one=candles(root/f"{symbol}-1m-{month}.zip",60000)
        funding=[(t,float(r[2])) for t,r in iter_rows(root/f"{symbol}-fundingRate-{month}.zip")]
        fund_times=[t for t,_ in funding]
        one_close=[b.available_at_ms for b in one]
        counts=Counter();returns=[];specialists=Counter();by_specialist={};by_regime={};by_direction={}
        next_allowed=0
        for i in range(63,len(five)-48,stride):
            decision=five[i].available_at_ms
            if decision<next_allowed:continue
            j=bisect.bisect_right(one_close,decision)
            if j<10:continue
            history=tuple(five[i-63:i+1]);confirm=tuple(one[j-10:j])
            future=tuple(five[i+1:i+49])
            try:
                ok,reason=__import__("signals_v2.backtest_exclusion_gate",fromlist=["eligible"]).eligible(
                    intervals,symbol,history[0].open_ms,future[0].open_ms,future[-1].available_at_ms)
                if not ok:counts["excluded_"+reason["reason"]]+=1;continue
                proposals=candidates(MarketSnapshot(symbol,decision,history,confirm))
                counts["scans"]+=1
                if not proposals:continue
                # Deterministic first candidate; no simultaneous overlapping trades per symbol.
                p=proposals[0];counts["proposals"]+=len(proposals)
                # Funding is charged only at actual payment times during holding.
                # First pass uses full horizon; report costs conservatively, not a live fill.
                fstart=bisect.bisect_right(fund_times,future[0].open_ms)
                fend=bisect.bisect_right(fund_times,future[-1].available_at_ms)
                provisional=guarded_replay(p,history,future,intervals,max_bars=48)
                actual_end=future[provisional.bars_held-1].available_at_ms
                fend_actual=bisect.bisect_right(fund_times,actual_end)
                rate=sum(x[1] for x in funding[fstart:fend_actual])
                result=guarded_replay(p,history,future,intervals,max_bars=48,funding_rate_total=rate)
                returns.append(result.net_r);specialists[p.specialist]+=1
                for bucket,key in ((by_specialist,p.specialist),(by_regime,p.regime),(by_direction,p.direction)):
                    bucket.setdefault(key,[]).append(result.net_r)
                counts["trades"]+=1;counts[result.exit_reason]+=1
                next_allowed=actual_end
            except (DataRejected,ValueError,IndexError) as exc:
                counts["rejected_"+str(exc).split(":")[0]]+=1
        report["symbols"][symbol]={"counts":dict(counts),"specialists":dict(specialists),
          "breakdown":{name:{key:{"count":len(vals),"mean_net_r":sum(vals)/len(vals),"net_r_total":sum(vals),"win_rate":sum(v>0 for v in vals)/len(vals)} for key,vals in group.items()} for name,group in (("specialist",by_specialist),("regime",by_regime),("direction",by_direction))},
          "trades":len(returns),"mean_net_r":sum(returns)/len(returns) if returns else None,
          "net_r_total":sum(returns),"positive_net_r":sum(v>0 for v in returns),
          "fee_per_side":0.0005,"slippage_per_side":0.0002,
          "funding":"historical actual payment times"}
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory");p.add_argument("manifest")
    p.add_argument("--month",default="2026-09");p.add_argument("--stride",type=int,default=12)
    a=p.parse_args()
    if a.stride<1:raise SystemExit("stride_must_be_positive")
    result=run(Path(a.directory),a.manifest,a.month,a.stride)
    print(json.dumps(result,indent=2))
    Path(a.directory,"pilot_replay_report.json").write_text(json.dumps(result,indent=2)+"\n")
