"""Selection refinement using training-only sample and stability requirements."""
from pathlib import Path
from dataclasses import asdict,replace
from datetime import datetime,timezone
import json,pandas as pd
from .research import Candidate,Policy,load_bars,signals,simulate,save_json,benchmark
from .run_research import TRAIN_START,TRAIN_END,VALID_END,accepted,quarterly
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'reports/stability-round';out.mkdir(exist_ok=True)
    raw=json.loads((ROOT/'reports/development-leaderboard.json').read_text())
    eligible=[x for x in raw if x['development']['trades']>=60 and x['positive_quarter_fraction']>.5 and x['development']['max_drawdown']<.08 and x['development']['net_return']>0]
    chosen=[]
    for family in ['ema','breakout','rsi_pullback']:
        rows=[x for x in eligible if x['candidate']['family']==family]
        if rows:chosen.append(rows[0])
    if (out/'preregistered-selection.json').exists():raise RuntimeError('Stability selection already registered')
    save_json(out/'preregistered-selection.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'selection':'Best training score per original family after 60 trades, >50% profitable training quarters, <8% training DD, positive training net return.',
       'selected_keys':[x['key'] for x in chosen],'validation_reused':True,'holdout_accessed':False,'new_parameter_configurations':0})
    results=[]
    for x in chosen:
        c=Candidate(**x['candidate']);df=load_bars(ROOT/'data/btcusdt_1h.csv',c.hours);df=df.loc[df.index<pd.Timestamp(VALID_END)];sig=signals(df,c)
        r=simulate(df,c,TRAIN_END,VALID_END,signal_frame=sig)
        stress=simulate(df,c,TRAIN_END,VALID_END,replace(Policy(),fee=.002,slippage=.001),sig)
        qs=quarterly(df,c,TRAIN_END,VALID_END,Policy(),sig);g=accepted(r['metrics'],30)
        g['positive_under_double_costs']=stress['metrics']['net_return']>0;g['majority_positive_quarters']=sum(q['net_return']>0 for q in qs)>len(qs)/2
        r.update({'key':c.key,'gates':g,'passed':all(g.values()),'double_cost_metrics':stress['metrics'],'quarters':qs,'validation_is_reused':True,'final_holdout_accessed':False})
        save_json(out/(c.key+'.json'),r)
        results.append({'key':c.key,'candidate':asdict(c),'metrics':r['metrics'],'gates':g,'passed':r['passed']})
    save_json(out/'summary.json',results);print(json.dumps(results,indent=2))
if __name__=='__main__':main()
