"""Explicit one-shot research capture: public discovery, bounded collection, JSONL.

Never schedules itself, sends orders, or claims complete historical coverage.
"""
from signals_v3.discover_current_price_candidates import capture_current_candidates
from signals_v3.persist_current_capture import append_current_capture

def run_one_shot(output,fetch=None,limit=10,clock_ms=None):
    kwargs={"limit":limit}
    if fetch is not None:
        kwargs["fetch"]=fetch
    if clock_ms is not None:
        kwargs["clock_ms"]=clock_ms
    capture=capture_current_candidates(**kwargs)
    result=append_current_capture(output,capture)
    return {"current_only":True,"historical_universe_verified":False,
            "candidate_count":capture["candidate_count"],
            "captured_count":capture["captured_count"],
            "complete_market_capture":capture["complete_market_capture"],
            "output":result["path"]}

if __name__=="__main__":
    import argparse,json
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--limit",type=int,default=10)
    args=parser.parse_args()
    print(json.dumps(run_one_shot(args.output,limit=args.limit),sort_keys=True))
