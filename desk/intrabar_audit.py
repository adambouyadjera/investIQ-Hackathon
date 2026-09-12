"""Audit four-hour execution ambiguity using constituent hourly OHLC data."""
import json
from pathlib import Path
import pandas as pd
from .research import load_bars,save_json,signals,Candidate
ROOT=Path(__file__).resolve().parents[1]
def main():
    hourly=load_bars(ROOT/'data/btcusdt_1h.csv',1)
    rows=[]
    paths=[ROOT/'reports/validation.json',ROOT/'reports/round-two/validation.json',ROOT/'reports/round-ml/validation.json',ROOT/'reports/stability-round/breakout_4h_40_20_atr3.json']
    for path in paths:
        r=json.loads(path.read_text());stop_n=sum(t['reason']=='stop' for t in r['trades']);target_n=sum(t['reason']=='target' for t in r['trades'])
        holding=[];ambiguous=0;hourly_target_first=0;unresolved_hourly=0
        c=Candidate(**r['candidate']);four=load_bars(ROOT/'data/btcusdt_1h.csv',c.hours)
        from .models import ridge_signals
        sig=ridge_signals(four.loc[four.index<pd.Timestamp('2026-04-01T00:00:00Z')],c)[0] if c.family=='ridge' else signals(four,c)
        for t in r['trades']:
            entry_time=pd.Timestamp(t['entry_time']);exit_time=pd.Timestamp(t['exit_time'])
            prior=four.index.get_loc(entry_time)-1
            distance=float(sig.loc[four.index[prior],'atr'])*c.stop_atr
            stop=t['entry_price']-distance;target=t['entry_price']+distance*c.reward_r
            bar=four.loc[exit_time]
            if t['reason'] in ('stop','target') and bar.low<=stop and bar.high>=target:
                ambiguous+=1
                sub=hourly.loc[(hourly.index>=exit_time)&(hourly.index<exit_time+pd.Timedelta(hours=c.hours))]
                for _,hb in sub.iterrows():
                    if hb.low<=stop and hb.high>=target:unresolved_hourly+=1;break
                    if hb.low<=stop:break
                    if hb.high>=target:hourly_target_first+=1;break
            holding.append((pd.Timestamp(t['exit_time'])-pd.Timestamp(t['entry_time'])).total_seconds()/3600)
        rows.append({'report':str(path.relative_to(ROOT)),'stop_exits':stop_n,'target_exits':target_n,
                     'signal_exits':sum(t['reason']=='signal' for t in r['trades']),
                     'median_holding_hours':float(pd.Series(holding).median()),
                     'ambiguous_four_hour_exits':ambiguous,'hourly_target_precedes_stop':hourly_target_first,'still_ambiguous_with_hourly_data':unresolved_hourly,
                     'window_end_exits':sum(t['reason']=='window_end' for t in r['trades']),
                     'note':'Four-hour OHLC cannot establish the order of stop/target touches; stop-first is used. No tick-level parity claim.'})
    save_json(ROOT/'reports/execution-audit.json',{'audits':rows,'source_market':'Binance spot',
      'fill_model':'Next-open signals, adverse slippage, stop-first ambiguous candles, worse price on stop gaps.',
      'funding':'Not applicable to unleveraged spot. These results cannot be transferred to perpetual futures without funding and venue validation.',
      'drawdown_definition':'Worst adverse intrabar liquidation mark relative to previous/current closing equity peak; not a tick-level drawdown.',
      'hourly_data_rows':len(hourly)})
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
