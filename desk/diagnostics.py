"""Research diagnostics on already inspected development/validation data only."""
from __future__ import annotations
import json,itertools
from pathlib import Path
from dataclasses import replace,asdict
import numpy as np
import pandas as pd
from .research import Candidate,Policy,load_bars,signals,simulate,save_json
from .run_research import TRAIN_START,TRAIN_END,VALID_END
ROOT=Path(__file__).resolve().parents[1]

def block_bootstrap(returns,reps=5000,block_days=7,seed=20260912):
    x=np.asarray(returns);rng=np.random.default_rng(seed);n=len(x)
    if n<block_days*2:return {'error':'insufficient observations'}
    totals=[];drawdowns=[]
    for _ in range(reps):
        starts=rng.integers(0,n,size=(n+block_days-1)//block_days)
        ix=(starts[:,None]+np.arange(block_days)[None,:])%n
        r=x[ix.ravel()[:n]];equity=np.cumprod(1+r)
        peak=np.maximum.accumulate(np.r_[1.,equity])[:-1]
        totals.append(float(equity[-1]-1));drawdowns.append(float(np.max(1-equity/peak)))
    return {'method':'circular moving-block resampling of daily strategy returns; descriptive, not a forecast or selection-adjusted significance test',
            'repetitions':reps,'block_days':block_days,'seed':seed,
            'return_percentiles':dict(zip(['p2_5','p50','p97_5'],map(float,np.percentile(totals,[2.5,50,97.5])))),
            'drawdown_percentiles':dict(zip(['p50','p95'],map(float,np.percentile(drawdowns,[50,95])))),
            'fraction_nonpositive_returns':float(np.mean(np.array(totals)<=0))}

def main():
    reports=ROOT/'reports';r=json.loads((reports/'validation.json').read_text());c=Candidate(**r['candidate'])
    df=load_bars(ROOT/'data/btcusdt_1h.csv',c.hours);df=df.loc[df.index<pd.Timestamp(VALID_END)]
    sig=signals(df,c)
    cost=[]
    for mult in [0,0.5,1,1.5,2,3]:
        p=replace(Policy(),fee=Policy().fee*mult,slippage=Policy().slippage*mult)
        run=simulate(df,c,TRAIN_END,VALID_END,p,sig)
        cost.append({'multiplier':mult,**run['metrics']})
    # Local neighbourhood around the frozen candidate; never used to select on the final holdout.
    local=[]
    for fast,slow,stop in itertools.product([16,20,24],[8,10,12],[1.5,2.,2.5]):
        nc=replace(c,fast=fast,slow=slow,stop_atr=stop)
        run=simulate(df,nc,TRAIN_START,TRAIN_END)
        local.append({'candidate':asdict(nc),**run['metrics']})
    values=pd.Series([x['equity'] for x in r['curve']],index=pd.to_datetime([x['time'] for x in r['curve']])).resample('1D').last().dropna()
    daily=values.pct_change().fillna(values.iloc[0]/10000-1)
    boot={str(b):block_bootstrap(daily,block_days=b) for b in [3,7,14]}
    # Test whether parameter ranks travel across calendar periods. Exploratory on training only.
    leaderboard=json.loads((reports/'development-leaderboard.json').read_text())
    quarter_matrix=np.array([[q['net_return'] for q in x['quarterly']] for x in leaderboard]).T
    ranks=[]
    for split in range(4,11):
        train=quarter_matrix[:split].mean(axis=0);future=quarter_matrix[split:split+2].mean(axis=0)
        winner=int(np.argmax(train));percentile=float(np.mean(future<=future[winner]))
        ranks.append({'training_quarters':split,'winner':leaderboard[winner]['key'],'next_two_quarters_mean':float(future[winner]),'future_percentile':percentile})
    out={'candidate':asdict(c),'cost_sensitivity':cost,'local_training_neighbourhood':local,
         'local_positive_fraction':float(np.mean([x['net_return']>0 for x in local])),
         'bootstrap_validation':boot,'training_walk_forward_rank_stability':ranks,
         'additional_configurations':len(local),'holdout_accessed':False}
    save_json(reports/'diagnostics.json',out)
    print(json.dumps({k:v for k,v in out.items() if k not in ['local_training_neighbourhood']},indent=2))

if __name__=='__main__':main()
