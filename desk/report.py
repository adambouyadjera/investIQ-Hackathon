"""Build a compact, honest research snapshot for the InvestIQ website."""
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import asdict
import json
from .research import Policy,save_json
ROOT=Path(__file__).resolve().parents[1]
NAMES={'ema':'EMA trend crossover','breakout':'Channel breakout','trend_breakout':'Trend-filtered breakout','rsi_pullback':'RSI pullback','ridge':'Local ridge model','tree':'Local boosted-tree model'}

def read(path,default=None):
    p=ROOT/path
    return json.loads(p.read_text()) if p.exists() else default

def make_report():
    all_rows=[]
    for folder in ['', 'round-two','round-ml','round-tree']:
        all_rows.extend(read(Path('reports')/folder/'development-leaderboard.json',[]))
    validations=[]
    paths=['reports/validation.json','reports/round-two/validation.json','reports/round-ml/validation.json','reports/round-tree/validation.json']
    for x in read('reports/stability-round/summary.json',[]):paths.append('reports/stability-round/'+x['key']+'.json')
    for path in paths:
        r=read(path)
        if not r:continue
        c=r['candidate'];k=next((x['key'] for x in all_rows if x['candidate']==c),path)
        curve=r['curve'];step=max(1,len(curve)//180)
        sampled=curve[::step]
        if sampled[-1]!=curve[-1]:sampled.append(curve[-1])
        validations.append({'key':k,'name':NAMES[c['family']],'candidate':c,'metrics':r['metrics'],
            'stress':r.get('double_cost_metrics'),'gates':r.get('gates',{}),'passed':r.get('passed',False),
            'validation_reused':r.get('validation_is_reused',False),'curve':sampled,
            'trades':r['trades'][-30:],'report_path':path})
    lookup={v['key']:v for v in validations}
    leaderboard=[{'key':r['key'],'name':NAMES[r['candidate']['family']],'candidate':r['candidate'],
                  'development':r['development'],'score':r['score'],
                  'validation':lookup[r['key']]['metrics'] if r['key'] in lookup else None} for r in all_rows]
    leaderboard.sort(key=lambda r:r['score'],reverse=True)
    now=datetime.now(timezone.utc)
    state=read('reports/research-state.json',{})
    result={'generated_at':now.isoformat(),'research_state':state,'symbol':'BTC/USDT','market':'Binance spot',
      'policy':asdict(Policy()),'data':read('data/btcusdt_1h.meta.json',{}),
      'configurations_tested':len(all_rows),'sensitivity_checks':27,'validated_candidates':len(validations),
      'passed_candidates':sum(v['passed'] for v in validations),'validation_start':'2025-01-01','validation_end':'2026-03-31',
      'development_start':'2022-01-01','development_end':'2024-12-31','holdout_status':'Sealed — no candidate has passed validation',
      'holdout_start':'2026-04-01','leaderboard':leaderboard,'validations':validations,
      'decision':read('state/selection.json',{}),'selection_audit':read('reports/selection-audit.json',{}),
      'forecast_audit':read('reports/forecast-audit.json',[]),'archive_audit':read('reports/archive-audit.json',{}),
      'benchmarks':{'cash':{'net_return':0.,'max_drawdown':0.},
                    'buy_hold':read('reports/validation.json',{}).get('benchmark_buy_hold'),
                    'half_exposure':read('reports/validation.json',{}).get('benchmark_half_exposure')},
      'operating_costs':'Free public data and local calculations. No paid APIs or Trader.dev credits. Scheduled Codex research uses the existing account allowance.',
      'notes':['Historical simulations, not account returns.','Repeated validation results are exploratory; no claim of fresh out-of-sample evidence.',
               'Signals use completed bars and enter at the next open in backtests. Paper entries use the price observed when the service runs.',
               'Fees: 0.10% per side; slippage: 0.05% per side. These are modelling assumptions. Doubled-cost tests apply 0.20% + 0.10% per side.',
               'No funding applies to unleveraged spot. Futures would require a separate test.',
               'A two-hour research window is not a profitability guarantee.'],
      'sources':[{'title':'Binance public market data','url':'https://developers.binance.com/en/docs/products/spot/rest-api'},
                 {'title':'Binance historical data archive','url':'https://github.com/binance/binance-public-data'},
                 {'title':'The probability of backtest overfitting','url':'https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf'},
                 {'title':'Machine learning and BTC trading costs','url':'https://arxiv.org/abs/2606.00060'}]}
    save_json(ROOT/'reports/summary.json',result)
    return result
if __name__=='__main__':
    r=make_report();print(f"{r['configurations_tested']} configurations; {r['validated_candidates']} validation checks; {r['passed_candidates']} passed")
