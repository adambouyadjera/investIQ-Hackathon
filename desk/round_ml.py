from pathlib import Path
from dataclasses import asdict,replace
from datetime import datetime,timezone
import numpy as np,pandas as pd,json
from .research import Candidate,Policy,load_bars,simulate,save_json
from .models import ridge_signals
from .run_research import TRAIN_START,TRAIN_END,VALID_END,quarterly,accepted
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'reports/round-ml';out.mkdir(exist_ok=True)
    cs=[Candidate('ridge',4,a,t,3.,3.) for a in [10,100] for t in [30,60,100]]
    if (out/'preregistered-grid.json').exists():raise RuntimeError('ML round already registered')
    save_json(out/'preregistered-grid.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),
       'hypothesis':'Forecast 24h BTC return using ten causal price/volume features; a cost buffer avoids small forecasts.',
       'model':'Ridge linear regression, standardized only on training data, rolling 365 days, monthly refit, six-bar label purge',
       'candidates':[asdict(c) for c in cs],'validation_reused':True,'holdout_accessed':False})
    df=load_bars(ROOT/'data/btcusdt_1h.csv',4);df=df.loc[df.index<pd.Timestamp(VALID_END)]
    # Reset features after gaps; skip at least 200 bars after a gap to avoid crossing its indicator warm-up.
    rows=[];cached={}
    for c in cs:
        sig,fits=ridge_signals(df,c);cached[c.key]=(sig,fits)
        r=simulate(df,c,TRAIN_START,TRAIN_END,signal_frame=sig)
        qs=quarterly(df,c,TRAIN_START,TRAIN_END,Policy(),sig);m=r['metrics']
        score=m['net_return']-.5*m['max_drawdown']+float(np.median([q['net_return'] for q in qs]))+.02*(float(np.mean([q['net_return']>0 for q in qs]))-.5)
        rows.append({'key':c.key,'candidate':asdict(c),'development':m,'score':score,'quarterly':qs})
        print(c.key,m['net_return'],m['max_drawdown'],flush=True)
    rows.sort(key=lambda r:r['score'],reverse=True);save_json(out/'development-leaderboard.json',rows)
    c=Candidate(**rows[0]['candidate']);sig,fits=cached[c.key]
    save_json(out/'frozen-candidate.json',{'candidate':asdict(c),'key':c.key,'frozen_at':datetime.now(timezone.utc).isoformat()})
    save_json(out/'fit-audit.json',fits)
    r=simulate(df,c,TRAIN_END,VALID_END,signal_frame=sig)
    stress=simulate(df,c,TRAIN_END,VALID_END,replace(Policy(),fee=.002,slippage=.001),sig)
    qs=quarterly(df,c,TRAIN_END,VALID_END,Policy(),sig);g=accepted(r['metrics'],30)
    g['positive_under_double_costs']=stress['metrics']['net_return']>0;g['majority_positive_quarters']=sum(q['net_return']>0 for q in qs)>len(qs)/2
    r.update({'gates':g,'passed':all(g.values()),'double_cost_metrics':stress['metrics'],'quarters':qs,'validation_is_reused':True,'final_holdout_accessed':False})
    save_json(out/'validation.json',r)
    print(json.dumps({'selected':c.key,'metrics':r['metrics'],'gates':g},indent=2))
if __name__=='__main__':main()
