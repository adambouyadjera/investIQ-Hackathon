"""Public BTCUSDT spot candles. No private endpoint or order API exists here."""
from __future__ import annotations
import csv, hashlib, json, math, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
HOUR = 3_600_000
BASE = 'https://data-api.binance.vision'
def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
def get_json(path, params=None):
    if path not in {'/api/v3/klines', '/api/v3/time', '/api/v3/exchangeInfo'}:
        raise ValueError('Only public market-data endpoints are permitted')
    url = BASE + path + ('?' + urlencode(params) if params else '')
    p = subprocess.run(['curl','--fail-with-body','--silent','--show-error','--max-time','30',url],capture_output=True,text=True)
    if p.returncode:
        raise RuntimeError(f'Public market data request failed ({p.returncode}): {p.stdout[:240]}')
    result=json.loads(p.stdout)
    if isinstance(result,dict) and 'code' in result and result['code']<0:
        raise RuntimeError(f'Market data error: {result}')
    return result

def normalize(rows, now_ms):
    clean=[]
    for row in rows:
        ts,ct=int(row[0]),int(row[6])
        if ct>=now_ms: continue
        o,h,l,c,v=map(float,row[1:6])
        if ts%HOUR or ct!=ts+HOUR-1: raise ValueError('Invalid hourly timestamp alignment')
        if not all(math.isfinite(x) for x in [o,h,l,c,v]): raise ValueError('Nonfinite candle')
        if min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h): raise ValueError('Invalid OHLCV values')
        clean.append({'time':ts,'open':o,'high':h,'low':l,'close':c,'volume':v})
    if any(b['time']<=a['time'] for a,b in zip(clean,clean[1:])): raise ValueError('Duplicate or unordered candles')
    return clean

def fetch_history(path:Path,start_ms:int,end_ms:int|None=None):
    now_ms=int(get_json('/api/v3/time')['serverTime']);end_ms=min(end_ms or now_ms,now_ms)
    rows,cursor=[],start_ms
    cache=path.parent/'raw';cache.mkdir(parents=True,exist_ok=True)
    while cursor<end_ms:
        cached=cache/f'{cursor}.json'
        chunk=json.loads(cached.read_text()) if cached.exists() else get_json('/api/v3/klines',{'symbol':'BTCUSDT','interval':'1h','startTime':cursor,'endTime':end_ms-1,'limit':1000})
        if len(chunk)==1000 and int(chunk[-1][6])<now_ms: cached.write_text(json.dumps(chunk))
        if not chunk: break
        rows.extend(chunk);nxt=int(chunk[-1][0])+HOUR
        if nxt<=cursor: raise RuntimeError('History pagination made no progress')
        cursor=nxt
        print(f'Fetched {len(rows)} candles through {utc(int(chunk[-1][0]))}',flush=True)
    clean=[];rejected=[]
    for row in rows:
        try: clean.extend(normalize([row],now_ms))
        except ValueError as exc: rejected.append({'time':int(row[0]),'reason':str(exc)})
    if any(b['time']<=a['time'] for a,b in zip(clean,clean[1:])): raise ValueError('Duplicate/unordered paginated candles')
    if not clean: raise RuntimeError('No completed candles returned')
    gaps=[{'after':utc(a['time']),'before':utc(b['time']),'missing_hours':(b['time']-a['time'])//HOUR-1}
          for a,b in zip(clean,clean[1:]) if b['time']-a['time']!=HOUR]
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp')
    with temp.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(clean[0]));writer.writeheader();writer.writerows(clean)
    temp.replace(path)
    meta={'source':BASE+'/api/v3/klines','symbol':'BTCUSDT','market':'Binance spot','interval':'1h',
          'fetched_at':utc(now_ms),'start':utc(clean[0]['time']),'last_open':utc(clean[-1]['time']),
          'last_close':utc(clean[-1]['time']+HOUR),'rows':len(clean),'gaps':gaps,'rejected_bars':rejected,
          'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix('.meta.json').write_text(json.dumps(meta,indent=2));return meta

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--start',default='2022-01-01');p.add_argument('--output',default='data/live_btcusdt_1h.csv');args=p.parse_args()
    start=int(datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc).timestamp()*1000)
    print(json.dumps(fetch_history(Path(args.output),start),indent=2))
