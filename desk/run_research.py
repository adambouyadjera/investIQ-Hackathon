"""Run the frozen development grid and validation; holdout requires an explicit phase."""
from __future__ import annotations
import argparse,json,hashlib
from pathlib import Path
from dataclasses import asdict,replace
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from .research import Candidate,Policy,grid,load_bars,signals,simulate,benchmark,save_json

ROOT=Path(__file__).resolve().parents[1]
TRAIN_START='2022-01-01T00:00:00Z';TRAIN_END='2025-01-01T00:00:00Z'
VALID_END='2026-04-01T00:00:00Z'

def quarterly(df,c,start,end,p,sig):
    bounds=pd.date_range(start,end,freq='QS',tz='UTC')
    return [simulate(df,c,a,b,p,sig)['metrics'] for a,b in zip(bounds,bounds[1:])]

def accepted(m,min_trades):
    pf=m['profit_factor']
    return {'positive_return':m['net_return']>0,'profit_factor_at_least_1_10':pf is not None and pf>=1.1,
            'sufficient_trades':m['trades']>=min_trades,'drawdown_below_10pct':m['max_drawdown']<.10,'no_risk_stop':not m['halted']}

def development():
    reports=ROOT/'reports'
    if (reports/'development-leaderboard.json').exists(): raise RuntimeError('Initial development results already exist. Use a new dated experiment directory; preserve frozen evidence.')
    plan=json.loads((reports/'preregistered-grid.json').read_text())
    candidates=[Candidate(**x) for x in plan['candidates']]
    bars={h:load_bars(ROOT/'data/btcusdt_1h.csv',h) for h in (1,4)}
    # Cut off the untouched final holdout at the data boundary, before computing signals.
    bars={h:df.loc[df.index<pd.Timestamp(VALID_END)] for h,df in bars.items()}
    rows=[];p=Policy()
    for n,c in enumerate(candidates,1):
        df=bars[c.hours];sig=signals(df,c)
        run=simulate(df,c,TRAIN_START,TRAIN_END,p,sig)
        qs=quarterly(df,c,TRAIN_START,TRAIN_END,p,sig)
        med=float(np.median([x['net_return'] for x in qs]));fraction=float(np.mean([x['net_return']>0 for x in qs]))
        m=run['metrics'];score=m['net_return']-.5*m['max_drawdown']+med+.02*(fraction-.5)
        rows.append({'key':c.key,'candidate':asdict(c),'development':m,'quarterly':qs,'score':score,'positive_quarter_fraction':fraction})
        print(f'{n:02}/{len(candidates)} {c.key}: development {m["net_return"]:.2%}, DD {m["max_drawdown"]:.2%}',flush=True)
    rows.sort(key=lambda x:x['score'],reverse=True)
    save_json(reports/'development-leaderboard.json',rows)
    pd.DataFrame([{'rank':i+1,'key':x['key'],'score':x['score'],**x['development'],'positive_quarter_fraction':x['positive_quarter_fraction']} for i,x in enumerate(rows)]).to_csv(reports/'development-leaderboard.csv',index=False)
    champion=rows[0];c=Candidate(**champion['candidate']);df=bars[c.hours];sig=signals(df,c)
    frozen={'frozen_at':datetime.now(timezone.utc).isoformat(),'candidate':asdict(c),'key':c.key,
            'selection':'Highest frozen development score; validation and holdout not used for ranking',
            'grid_sha256':hashlib.sha256((reports/'preregistered-grid.json').read_bytes()).hexdigest(),
            'data_sha256':hashlib.sha256((ROOT/'data/btcusdt_1h.csv').read_bytes()).hexdigest()}
    save_json(reports/'frozen-candidate.json',frozen)
    validation=simulate(df,c,TRAIN_END,VALID_END,p,sig)
    stress=simulate(df,c,TRAIN_END,VALID_END,replace(p,fee=p.fee*2,slippage=p.slippage*2),sig)
    quarters=quarterly(df,c,TRAIN_END,VALID_END,p,sig)
    gates=accepted(validation['metrics'],30)
    gates['positive_under_double_costs']=stress['metrics']['net_return']>0
    gates['majority_positive_quarters']=sum(q['net_return']>0 for q in quarters)>len(quarters)/2
    validation.update({'double_cost_metrics':stress['metrics'],'quarters':quarters,'gates':gates,'passed':all(gates.values()),
                       'benchmark_buy_hold':benchmark(df,TRAIN_END,VALID_END,p),
                       'benchmark_half_exposure':benchmark(df,TRAIN_END,VALID_END,p,.5),'policy':asdict(p)})
    save_json(reports/'validation.json',validation)
    print('FROZEN CANDIDATE',c.key,flush=True)
    print(json.dumps({'validation':validation['metrics'],'gates':gates,'stress':stress['metrics']},indent=2))

def holdout():
    reports=ROOT/'reports';target=reports/'holdout.json'
    if target.exists(): raise RuntimeError('Holdout already opened. Preserve it; do not reuse it as fresh validation.')
    frozen=json.loads((reports/'frozen-candidate.json').read_text());c=Candidate(**frozen['candidate'])
    valid=json.loads((reports/'validation.json').read_text())
    df=load_bars(ROOT/'data/btcusdt_1h.csv',c.hours)
    end=df.index[-1]+pd.Timedelta(hours=c.hours)
    r=simulate(df,c,VALID_END,end,Policy())
    gates=accepted(r['metrics'],15)
    gates['validation_passed']=valid['passed']
    r.update({'gates':gates,'passed':all(gates.values()),'opened_at':datetime.now(timezone.utc).isoformat(),
              'previously_inspected_after_this_run':True,'frozen_candidate':frozen,
              'benchmark_buy_hold':benchmark(df,VALID_END,end),'benchmark_half_exposure':benchmark(df,VALID_END,end,exposure=.5),
              'policy':asdict(Policy())})
    save_json(target,r)
    decision={'mode':'paper','eligible':r['passed'],'candidate':asdict(c) if r['passed'] else None,
              'research_candidate':asdict(c),'reason':'Passed preregistered gates' if r['passed'] else 'Failed preregistered gates; cash only',
              'gates':gates,'decided_at':datetime.now(timezone.utc).isoformat(),
              'holdout_end':end.isoformat(),'min_forward_observation_days':14,'live_execution_enabled':False}
    save_json(ROOT/'state/selection.json',decision)
    print(json.dumps({'holdout':r['metrics'],'gates':gates,'paper_eligible':r['passed']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['development','holdout']);a=p.parse_args()
    development() if a.phase=='development' else holdout()
