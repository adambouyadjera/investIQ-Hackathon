"""Free hourly maintenance. Research decisions are made in the Codex task."""
import json
from datetime import datetime, timezone
from .paper import ROOT, locked, atomic_json, cycle_all
from .market import fetch_history
from .report import make_report

def run():
    with locked(ROOT/'state/hourly.lock'):
        result={'at':datetime.now(timezone.utc).isoformat(),'status':'ok'}
        try:
            result['data']=fetch_history(ROOT/'data/live_btcusdt_1h.csv',1640995200000)
            result['paper']=cycle_all()
            make_report()
        except (RuntimeError,OSError,ValueError) as exc:
            result.update(status='failed',error=str(exc))
        atomic_json(ROOT/'reports/last-hourly-run.json',result)
        return result
if __name__=='__main__':
    result=run();print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='ok' else 1)
