"""One-hour research feed observation; read-only, no simulated or real orders."""
import json,time
from pathlib import Path
from datetime import datetime,timezone
from .market import get_json,normalize,utc,HOUR
ROOT=Path(__file__).resolve().parents[1]
def observe(deadline):
    path=ROOT/'reports/feed-observations.jsonl';seen={}
    while True:
        now=datetime.now(timezone.utc);result={'observed_at':now.isoformat()}
        try:
            server=int(get_json('/api/v3/time')['serverTime'])
            rows=normalize(get_json('/api/v3/klines',{'symbol':'BTCUSDT','interval':'1h','limit':3}),server)
            changes=[r['time'] for r in rows if r['time'] in seen and seen[r['time']]!=r]
            seen.update({r['time']:r for r in rows})
            result.update({'server_time':utc(server),'last_completed_open':utc(rows[-1]['time']),
                           'completed_bar_age_seconds':(server-rows[-1]['time']-HOUR)/1000,
                           'closed_candle_revisions':changes,'ok':not changes})
        except Exception as e: result.update({'ok':False,'error':str(e)})
        with path.open('a') as f:f.write(json.dumps(result)+'\n')
        print(json.dumps(result),flush=True)
        if now>=deadline: break
        time.sleep(min(60,max(1,(deadline-now).total_seconds())))
if __name__=='__main__':
    import sys
    observe(datetime.fromisoformat(sys.argv[1]))
