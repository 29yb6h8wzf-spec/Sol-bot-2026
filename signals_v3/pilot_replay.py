"""V3 offline historical pilot; exploratory only, never OOS certification.

Uses archived ZIPs and the existing conservative V2 replay accounting.
No Binance API, orders, secrets, or deployment.
"""
import argparse,bisect,json
from collections import Counter
from pathlib import Path
from signals_v2.contracts import DataRejected,MarketSnapshot
from signals_v2.hybrid import Hypothesis
from signals_v2.guarded_replay import guarded_replay
from signals_v2.backtest_exclusion_gate import load_manifest,eligible
from signals_v2.pilot_replay import candles
from signals_v2.enumerate_all_mismatches import iter_rows
from signals_v3.router import candidates

def replay_hypothesis(signal):
    if not signal.research_only or signal.execution_authorized:
        raise DataRejected("v3_signal_not_research_only")
    return Hypothesis("signals.v3.research.1",signal.symbol,signal.direction,
        signal.strategy,"V3_EXPLORATORY",signal.decision_ms,signal.entry_reference,
        signal.stop_reference,signal.target_reference,signal.decision_ms+600000)

def run(root,manifest,month="2026-09",stride=12):
    if type(stride)!=int or stride<1:raise ValueError("invalid_stride")
    intervals=load_manifest(manifest)
    report={"schema":"signals.v3.pilot.1","month":month,"stride_5m_bars":stride,
        "research_only":True,"out_of_sample_certified":False,"profitability_proven":False,
        "symbols":{}}
    for symbol in ("SOLUSDT","XRPUSDT"):
        five=candles(root/f"{symbol}-5m-{month}.zip",300000)
        one=candles(root/f"{symbol}-1m-{month}.zip",60000)
        funding=[(t,float(row[2])) for t,row in iter_rows(root/f"{symbol}-fundingRate-{month}.zip")]
        fund_times=[t for t,_ in funding]
        one_times=[b.available_at_ms for b in one]
        counts=Counter();by_strategy={};returns=[];next_allowed=0
        for i in range(63,len(five)-48,stride):
            decision=five[i].available_at_ms
            if decision<next_allowed:continue
            j=bisect.bisect_right(one_times,decision)
            if j<45:continue
            history=tuple(five[i-63:i+1]);micro=tuple(one[j-45:j])
            future=tuple(five[i+1:i+49])
            ok,reason=eligible(intervals,symbol,history[0].open_ms,
                future[0].open_ms,future[-1].available_at_ms)
            if not ok:counts["excluded_"+reason["reason"]]+=1;continue
            try:
                proposals=candidates(symbol,history,micro,decision)
                counts["scans"]+=1
                counts["proposals"]+=len(proposals)
                if not proposals:continue
                # Deterministic first hypothesis; never overlap within a symbol.
                proposal=replay_hypothesis(proposals[0])
                provisional=guarded_replay(proposal,history,future,intervals,max_bars=48)
                actual_end=future[provisional.bars_held-1].available_at_ms
                start=bisect.bisect_right(fund_times,future[0].open_ms)
                end=bisect.bisect_right(fund_times,actual_end)
                rate=sum(x[1] for x in funding[start:end])
                result=guarded_replay(proposal,history,future,intervals,
                    max_bars=48,funding_rate_total=rate)
                returns.append(result.net_r)
                by_strategy.setdefault(proposal.specialist,[]).append(result.net_r)
                counts["trades"]+=1;counts[result.exit_reason]+=1
                next_allowed=actual_end
            except (DataRejected,ValueError,IndexError) as exc:
                counts["rejected_"+str(exc).split(":")[0]]+=1
        report["symbols"][symbol]={"counts":dict(counts),"trades":len(returns),
            "mean_net_r":sum(returns)/len(returns) if returns else None,
            "net_r_total":sum(returns),
            "strategies":{k:{"trades":len(v),"mean_net_r":sum(v)/len(v),
                "net_r_total":sum(v)} for k,v in by_strategy.items()},
            "fees_per_side":0.0005,"slippage_per_side":0.0002,
            "funding":"historical actual payment times"}
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("directory");parser.add_argument("manifest")
    parser.add_argument("--month",default="2026-09")
    parser.add_argument("--stride",type=int,default=12)
    args=parser.parse_args()
    result=run(Path(args.directory),args.manifest,args.month,args.stride)
    print(json.dumps(result,indent=2))
    (Path(args.directory)/"v3_pilot_replay_report.json").write_text(
        json.dumps(result,indent=2)+"\n")
