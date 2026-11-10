"""Cross-timeframe OHLCV and funding-content quality gate for monthly archives.

No synthetic candles. The known missing UTC day is excluded from aggregation.
"""
import argparse,csv,io,json,math,zipfile
from pathlib import Path
from audit_segmented_history import months,ms,GAP_START,GAP_END

def rows(path):
    with zipfile.ZipFile(path) as z:
        names=[n for n in z.namelist() if n.endswith(".csv")]
        if len(names)!=1 or z.testzip() is not None:raise ValueError("bad_zip")
        with z.open(names[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8-sig")):
                if row and row[0].strip().isdigit():
                    t=int(row[0]);yield (t//1000 if t>=100000000000000 else t),row

def validate(root):
    results=[];errors=[]
    for symbol in ("SOLUSDT","XRPUSDT"):
        for year,month in months():
            prefix=f"{symbol}-"
            period=f"{year:04d}-{month:02d}.zip"
            try:
                one=rows(root/(prefix+"1m-"+period))
                five=rows(root/(prefix+"5m-"+period))
                n1=n5=0;matched=0
                block=[]
                current=next(five,None)
                for t,r in one:
                    n1+=1
                    if GAP_START<=t<GAP_END:raise ValueError("gap_has_unexpected_1m")
                    if block and t!=block[-1][0]+60000:
                        if block:raise ValueError("partial_1m_group")
                    block.append((t,r))
                    if len(block)<5:continue
                    if len(block)!=5 or block[0][0]%300000:raise ValueError("misaligned_1m")
                    if current is None:raise ValueError("missing_5m")
                    ft,fr=current;n5+=1
                    if ft!=block[0][0]:raise ValueError(f"5m_timestamp_mismatch:{ft}:{block[0][0]}")
                    vals=[[float(x[1][i]) for i in (1,2,3,4,5)] for x in block]
                    expected=[vals[0][0],max(v[1] for v in vals),min(v[2] for v in vals),vals[-1][3],sum(v[4] for v in vals)]
                    actual=[float(fr[i]) for i in (1,2,3,4,5)]
                    for a,b in zip(actual,expected):
                        if not math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-7):
                            raise ValueError(f"ohlcv_mismatch:{ft}:{a}:{b}")
                    matched+=1;block=[];current=next(five,None)
                if block:raise ValueError("trailing_partial_group")
                if current is not None:raise ValueError("extra_5m")
                fund_count=0
                last=None
                for t,row in rows(root/(prefix+"fundingRate-"+period)):
                    if last is not None and t<=last:raise ValueError("funding_order")
                    if len(row)<3:raise ValueError("funding_short_row")
                    # Official monthly funding CSV typically uses: calc_time, funding_interval_hours, last_funding_rate
                    # Validate at least one finite rate candidate; do not assume the column order.
                    numeric=[]
                    for x in row[1:]:
                        try:
                            v=float(x)
                            if math.isfinite(v):numeric.append(v)
                        except ValueError:pass
                    if not numeric:raise ValueError("funding_no_numeric_values")
                    last=t;fund_count+=1
                if fund_count==0:raise ValueError("empty_funding")
                results.append({"symbol":symbol,"month":f"{year:04d}-{month:02d}","matched_5m_candles":matched,"one_minute_candles":n1,"funding_rows":fund_count})
            except Exception as exc:
                errors.append({"symbol":symbol,"month":f"{year:04d}-{month:02d}","reason":str(exc)})
    return {"status":"PASS" if not errors and len(results)==48 else "FAIL","months_verified":len(results),"expected_months":48,"errors":errors,"results":results,"funding_schema_specific_validation":False,"profitability_proven":False}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("directory");a=p.parse_args()
    root=Path(a.directory);report=validate(root)
    (root/"quality_gate_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))
    if report["status"]!="PASS":raise SystemExit(1)
