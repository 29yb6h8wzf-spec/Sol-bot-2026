"""Offline end-to-end V3 archive coverage audit.

Uses a supplied acquisition plan and local files only. A successful job proves
audit plumbing, NOT historical universe eligibility or strategy profitability.
"""
import argparse,json
from pathlib import Path
from signals_v3.audit_local_archives import audit_plan
from signals_v3.archive_coverage_report import summarize,audit_expected_archive_grid

def run(plan_path,archive_root,output_dir):
    plan=json.loads(Path(plan_path).read_text())
    audit=audit_plan(plan,archive_root)
    report=summarize(audit)
    records=plan.get('records')
    if not isinstance(records,list) or not records:
        raise ValueError('missing_acquisition_plan_records')
    symbols=sorted({r['symbol'] for r in records})
    months=sorted({r['month'] for r in records})
    intervals=sorted({r['interval'] for r in records})
    report['archive_grid']=audit_expected_archive_grid(audit,symbols,months,intervals)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"archive_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    (out/"archive_coverage.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("plan");p.add_argument("--archive-root",required=True)
    p.add_argument("--output-dir",required=True);a=p.parse_args()
    report=run(a.plan,a.archive_root,a.output_dir)
    print(json.dumps({k:report[k] for k in ("total","verified","blocked","coverage_percent","dynamic_backtest_ready")}))
