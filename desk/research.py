"""Chronological, event-driven research. Signal generation never sees future bars."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib,itertools,json,math
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class Candidate:
    family:str
    hours:int
    fast:int
    slow:int
    stop_atr:float=2.0
    reward_r:float=2.0
    @property
    def key(self): return f'{self.family}_{self.hours}h_{self.fast}_{self.slow}_atr{self.stop_atr:g}' + (f'_r{self.reward_r:g}' if self.reward_r!=2 else '')

@dataclass(frozen=True)
class Policy:
    capital:float=10000
    fee:float=.001
    slippage:float=.0005
    risk:float=.005
    max_exposure:float=.5
    max_drawdown:float=.10
    qty_step:float=.00001
    min_notional:float=5


def grid():
    specs={'ema':[(10,50),(20,50),(20,100),(50,200)],
           'breakout':[(20,10),(40,20),(80,40),(120,60)],
           'rsi_pullback':[(7,25),(14,30),(14,35),(21,35)]}
    return [Candidate(f,h,a,b,s) for f, pairs in specs.items()
            for h in (1,4) for a,b in pairs for s in (2.0,3.0)]


def load_bars(path, hours=1):
    if hours not in (1,4): raise ValueError('Research timeframes are 1h and 4h')
    df=pd.read_csv(path)
    expected=['time','open','high','low','close','volume']
    if list(df.columns)!=expected: raise ValueError('Unexpected data schema')
    if not np.isfinite(df.to_numpy()).all(): raise ValueError('Nonfinite data')
    if df.time.duplicated().any() or not df.time.is_monotonic_increasing: raise ValueError('Duplicate/unordered data')
    if (df[['open','high','low','close']]<=0).any().any() or (df.volume<0).any(): raise ValueError('Invalid prices/volume')
    if ((df.high<df[['open','close','low']].max(axis=1)) | (df.low>df[['open','close','high']].min(axis=1))).any(): raise ValueError('Invalid OHLC')
    df.index=pd.to_datetime(df.time,unit='ms',utc=True)
    df=df.drop(columns='time')
    if hours!=1:
        count=df.close.resample(f'{hours}h').count()
        df=df.resample(f'{hours}h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
        df=df.loc[count==hours]
    df['gap']=df.index.to_series().diff().dt.total_seconds().fillna(hours*3600).ne(hours*3600)
    return df


def _segment_signals(df,c):
    close=df.close
    atr=pd.concat([df.high-df.low,(df.high-close.shift()).abs(),(df.low-close.shift()).abs()],axis=1).max(axis=1).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    if c.family=='ema':
        fast=close.ewm(span=c.fast,adjust=False,min_periods=c.fast).mean()
        slow=close.ewm(span=c.slow,adjust=False,min_periods=c.slow).mean()
        entry=(fast>slow)&(fast.shift()<=slow.shift())
        leave=(fast<slow)&(fast.shift()>=slow.shift())
    elif c.family in ('breakout','trend_breakout'):
        upper=df.high.rolling(c.fast).max().shift()
        lower=df.low.rolling(c.slow).min().shift()
        entry=(close>upper)&(close.shift()<=upper.shift())
        leave=close<lower
        if c.family=='trend_breakout':
            trend=close.ewm(span=200,adjust=False,min_periods=200).mean()
            entry=entry&(close>trend)&(trend>trend.shift(6))
    elif c.family=='rsi_pullback':
        d=close.diff();up=d.clip(lower=0).ewm(alpha=1/c.fast,adjust=False,min_periods=c.fast).mean()
        down=(-d.clip(upper=0)).ewm(alpha=1/c.fast,adjust=False,min_periods=c.fast).mean()
        rsi=100-100/(1+up/down.replace(0,np.nan));rsi=rsi.where(down!=0,100)
        trend=close.ewm(span=200,adjust=False,min_periods=200).mean()
        entry=(rsi>c.slow)&(rsi.shift()<=c.slow)&(close>trend)
        leave=(rsi>=65)|(close<trend)
    else: raise ValueError('Unknown strategy family')
    return pd.DataFrame({'entry':entry.fillna(False),'leave':leave.fillna(False),'atr':atr},index=df.index)


def signals(df,c):
    groups=df['gap'].cumsum() if 'gap' in df else pd.Series(0,index=df.index)
    return pd.concat([_segment_signals(part,c) for _,part in df.groupby(groups,sort=False)])


def position_qty(equity,price,distance,p):
    if not all(math.isfinite(x) and x>0 for x in (equity,price,distance)): return 0.0
    if distance>=price: return 0.0  # A long stop must have a positive price.
    estimated_loss=distance+price*(2*p.fee+2*p.slippage)
    raw=min(equity*p.risk/estimated_loss,equity*p.max_exposure/(price*(1+p.fee)))
    qty=math.floor(raw/p.qty_step)*p.qty_step
    return qty if qty*price>=p.min_notional else 0.0


def simulate(df,c,start,end,policy=Policy(),signal_frame=None):
    start=pd.Timestamp(start);end=pd.Timestamp(end)
    sig=signals(df,c) if signal_frame is None else signal_frame
    # Warm-up indicators are calculated on earlier bars; trades are restricted to [start,end).
    idx=np.flatnonzero((df.index>=start)&(df.index<end))
    if len(idx)<2: raise ValueError('Insufficient evaluation bars')
    o,h,l,cl=(df[k].to_numpy() for k in ['open','high','low','close'])
    ent,leave,atr=(sig[k].to_numpy() for k in ['entry','leave','atr'])
    gaps=df['gap'].to_numpy() if 'gap' in df else np.zeros(len(df),dtype=bool)
    cash=policy.capital;qty=0.;entry=stop=target=entry_fee=0.;entry_ts=None
    peak=policy.capital;worst=0.;halted=False;trades=[];curve=[];fees=0.;exposure_bars=0
    day=week=month=None;day_base=week_base=month_base=policy.capital
    def exit_position(i,raw,reason):
        nonlocal cash,qty,fees
        px=raw*(1-policy.slippage);cost=qty*px*policy.fee
        pnl=qty*(px-entry)-entry_fee-cost
        cash+=qty*px-cost;fees+=cost
        trades.append({'entry_time':entry_ts.isoformat(),'exit_time':df.index[i].isoformat(),
                       'entry_price':entry,'exit_price':px,'quantity':qty,'pnl':pnl,'reason':reason,
                       'fees':entry_fee+cost})
        qty=0.
    for i in idx:
        ts=df.index[i];equity_open=cash+qty*o[i]
        dk=ts.date();wk=ts.isocalendar()[:2];mk=(ts.year,ts.month)
        if dk!=day: day=dk;day_base=equity_open
        if wk!=week: week=wk;week_base=equity_open
        if mk!=month: month=mk;month_base=equity_open
        dr=equity_open/day_base-1;wr=equity_open/week_base-1;mr=equity_open/month_base-1
        multiplier=.5 if dr<=-.02 or wr<=-.05 else 1.
        blocked=halted or wr<=-.06 or mr<=-.10 or dr<-.03
        if qty and (gaps[i] or dr<-.03): exit_position(i,o[i],'data_gap' if gaps[i] else 'daily_stop')
        # Protective orders exist from entry; adverse gap fills precede signal exits.
        if qty and o[i]<=stop: exit_position(i,o[i],'gap_stop')
        elif qty and o[i]>=target: exit_position(i,target,'gap_target_conservative')
        elif qty and i>0 and leave[i-1]: exit_position(i,o[i],'signal')
        if not qty and not blocked and not gaps[i] and i>0 and ent[i-1] and math.isfinite(atr[i-1]):
            entry=o[i]*(1+policy.slippage);distance=c.stop_atr*atr[i-1]
            qty=position_qty(cash,entry,distance,policy)*multiplier
            qty=math.floor(qty/policy.qty_step)*policy.qty_step
            if qty:
                stop=entry-distance;target=entry+distance*c.reward_r
                entry_fee=qty*entry*policy.fee;cash-=qty*entry+entry_fee;fees+=entry_fee;entry_ts=ts
        if qty:
            exposure_bars+=1
            # Stop-first resolution when both barriers are touched; no optimistic bar path.
            adverse=max(l[i],stop) if o[i]>=stop else o[i]
            low_equity=cash+qty*adverse*(1-policy.slippage)*(1-policy.fee)
            worst=max(worst,1-low_equity/peak)
            if l[i]<=stop: exit_position(i,min(o[i],stop),'stop')
            elif h[i]>=target: exit_position(i,target,'target')
        eq=cash+qty*cl[i]
        peak=max(peak,eq);dd=1-eq/peak;worst=max(worst,dd)
        if worst>=policy.max_drawdown:
            halted=True
            if qty: exit_position(i,cl[i],'drawdown_stop');eq=cash
        curve.append({'time':ts.isoformat(),'equity':eq,'drawdown':dd,'exposed':bool(qty)})
    if qty:
        exit_position(idx[-1],cl[idx[-1]],'window_end')
        curve[-1]['equity']=cash;curve[-1]['exposed']=False
        worst=max(worst,1-cash/peak)
    values=np.array([policy.capital]+[x['equity'] for x in curve])
    returns=values[1:]/values[:-1]-1
    pnl=np.array([t['pnl'] for t in trades]);win=float(pnl[pnl>0].sum());loss=float(-pnl[pnl<0].sum())
    daily=pd.Series([x['equity'] for x in curve],index=df.index[idx]).resample('1D').last().dropna().pct_change().dropna()
    sharpe=float(daily.mean()/daily.std()*np.sqrt(365)) if len(daily)>1 and daily.std()>0 else 0.
    metrics={'net_return':float(cash/policy.capital-1),'final_equity':float(cash),'max_drawdown':float(worst),
             'trades':len(trades),'win_rate':float((pnl>0).mean()) if len(pnl) else 0.,
             'profit_factor':win/loss if loss else (None if win else 0.),'fees':float(fees),
             'daily_sharpe':sharpe,'exposure':exposure_bars/len(idx),'halted':halted,
             'start':df.index[idx[0]].isoformat(),'end':df.index[idx[-1]].isoformat(),'bars':len(idx)}
    return {'candidate':asdict(c),'metrics':metrics,'trades':trades,'curve':curve}


def benchmark(df,start,end,p=Policy(),exposure=1.):
    part=df.loc[(df.index>=pd.Timestamp(start))&(df.index<pd.Timestamp(end))]
    buy=part.open.iloc[0]*(1+p.slippage)
    qty=math.floor(p.capital*exposure/(buy*(1+p.fee))/p.qty_step)*p.qty_step
    cash=p.capital-qty*buy*(1+p.fee)
    eq=cash+qty*part.close
    final=cash+qty*part.close.iloc[-1]*(1-p.slippage)*(1-p.fee)
    peak=np.maximum.accumulate(np.r_[p.capital,eq.to_numpy()])[:-1]
    worst=float(np.max(1-(cash+qty*part.low.to_numpy())/peak))
    return {'net_return':float(final/p.capital-1),'max_drawdown':worst,'exposure_target':exposure}


def metrics_row(result,prefix=''):
    return {prefix+k:v for k,v in result['metrics'].items()}

def save_json(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False))
