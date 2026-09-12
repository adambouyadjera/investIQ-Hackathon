"""Bounded refinement. Validation was already inspected; final holdout remains sealed."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path
import json,numpy as np,pandas as pd
from .research import Candidate,Policy,load_bars,signals,simulate,save_json,benchmark
from .run_research import quarterly,accepted,TRAIN_START,TRAIN_END,VALID_END
ROOT=Path(__file__).resolve().parents[1]
def main():
    reports=ROOT/'reports';target=reports/'round-two'
    target.mkdir(exist_ok=True)
    cs=[Candidate('trend_breakout',4,a,b,s,r) for a,b in [(20,10),(40,20),(80,40)] for s in [2.,3.] for r in [2.,3.]]
    plan={'frozen_at':datetime.now(timezone.utc).isoformat(),'hypothesis':'A rising 200-period EMA filter plus longer reward targets may reduce countertrend entries and trading-cost drag.',
          'candidates':[asdict(c) for c in cs],'count':len(cs),
          'selection':'Rank on 2022–2024 ONLY using the same original score. Check selected candidate on reused validation. Do not evaluate any final holdout without a separate decision.',
          'validation_is_reused':True,'final_holdout_accessed':False}
    if (target/'preregistered-grid.json').exists():raise RuntimeError('Round two already registered')
    save_json(target/'preregistered-grid.json',plan)
    df=load_bars(ROOT/'data/btcusdt_1h.csv',4);df=df.loc[df.index<pd.Timestamp(VALID_END)]
    rows=[]
    for c in cs:
        sig=signals(df,c);r=simulate(df,c,TRAIN_START,TRAIN_END,signal_frame=sig)
        qs=quarterly(df,c,TRAIN_START,TRAIN_END,Policy(),sig)
        med=float(np.median([q['net_return'] for q in qs]));fraction=float(np.mean([q['net_return']>0 for q in qs]));m=r['metrics']
        score=m['net_return']-.5*m['max_drawdown']+med+.02*(fraction-.5)
        rows.append({'key':c.key,'candidate':asdict(c),'development':m,'score':score,'quarterly':qs})
        print(c.key,m['net_return'],m['max_drawdown'],flush=True)
    rows.sort(key=lambda r:r['score'],reverse=True);save_json(target/'development-leaderboard.json',rows)
    c=Candidate(**rows[0]['candidate']);save_json(target/'frozen-candidate.json',{'candidate':asdict(c),'key':c.key,'frozen_at':datetime.now(timezone.utc).isoformat()})
    sig=signals(df,c);r=simulate(df,c,TRAIN_END,VALID_END,signal_frame=sig)
    stress=simulate(df,c,TRAIN_END,VALID_END,replace(Policy(),fee=.002,slippage=.001),sig)
    qs=quarterly(df,c,TRAIN_END,VALID_END,Policy(),sig);g=accepted(r['metrics'],30)
    g['positive_under_double_costs']=stress['metrics']['net_return']>0;g['majority_positive_quarters']=sum(q['net_return']>0 for q in qs)>len(qs)/2
    r.update({'double_cost_metrics':stress['metrics'],'gates':g,'passed':all(g.values()),'validation_is_reused':True,'quarters':qs,'final_holdout_accessed':False})
    save_json(target/'validation.json',r)
    print(json.dumps({'selected':c.key,'metrics':r['metrics'],'gates':g},indent=2))
if __name__=='__main__':main()
