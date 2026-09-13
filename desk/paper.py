"""Persistent, isolated paper accounts. This module cannot submit exchange orders."""
from __future__ import annotations
import fcntl,json,math,os
from dataclasses import replace,asdict
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from .research import Candidate,Policy,position_qty,signals
from .market import get_json,normalize,HOUR,utc
ROOT=Path(__file__).resolve().parents[1]
NAMES={'ema':'EMA trend crossover','breakout':'Channel breakout','trend_breakout':'Trend-filtered breakout','rsi_pullback':'RSI pullback'}
EXIT_CODES={'modelled resting stop':'stop','modelled resting target':'target','requested close':'manual','risk stop':'risk','completed-bar signal':'signal'}
EXIT_TEXT={'stop':'The price fell to the loss limit, so the bot sold to stop the loss from growing.',
           'target':'The price rose to the profit target, so the bot sold to lock in the gain.',
           'manual':'You asked the bot to sell.',
           'risk':'A safety rule was hit (the account lost too much), so the bot sold everything.'}

def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False));os.replace(tmp,path)

@contextmanager
def locked(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f,fcntl.LOCK_UN)

def snapshot():
    server=int(get_json('/api/v3/time')['serverTime'])
    raw=get_json('/api/v3/klines',{'symbol':'BTCUSDT','interval':'1h','limit':1000})
    closed=normalize(raw,server)
    quote=float(raw[-1][4])
    return {'server_ms':server,'observed_ms':int(datetime.now(timezone.utc).timestamp()*1000),
            'price':quote,'bars':closed,'source':'Binance BTCUSDT spot public candles'}

def learning_candidate(summary_path=None):
    """Best validated strategy the signal engine can run. Traded only by accounts that opt in; it is NOT qualified."""
    try:
        d=json.loads(Path(summary_path or ROOT/'reports/summary.json').read_text())
        best=max((v for v in d['validations'] if v['candidate']['family'] in NAMES),key=lambda v:v['metrics']['net_return'])
        c=Candidate(**{k:best['candidate'][k] for k in ['family','hours','fast','slow','stop_atr','reward_r']})
        info={'net_return':best['metrics']['net_return'],'test_trades':best['metrics']['trades'],'failed_checks':[k for k,ok in best['gates'].items() if not ok]}
    except (OSError,ValueError,KeyError,TypeError):
        c=Candidate('breakout',4,40,20,3.0,2.0);info={'net_return':None,'test_trades':None,'failed_checks':[]}
    return c,{'key':c.key,'name':NAMES[c.family],'learning':True,**asdict(c),**info}

def _usd(x): return f'${x:,.2f}'

def signal_context(frame,c):
    close=frame.close;ctx={'close':float(close.iloc[-1])}
    if c.family in ('breakout','trend_breakout'):
        ctx['recent_high']=float(frame.high.rolling(c.fast).max().shift().iloc[-1])
        ctx['recent_low']=float(frame.low.rolling(c.slow).min().shift().iloc[-1])
    if c.family in ('trend_breakout','rsi_pullback'):
        ctx['long_average']=float(close.ewm(span=200,adjust=False,min_periods=200).mean().iloc[-1])
    if c.family=='ema':
        ctx['fast_average']=float(close.ewm(span=c.fast,adjust=False,min_periods=c.fast).mean().iloc[-1])
        ctx['slow_average']=float(close.ewm(span=c.slow,adjust=False,min_periods=c.slow).mean().iloc[-1])
    return {k:v for k,v in ctx.items() if math.isfinite(v)}

def entry_reason(c,ctx):
    span=f'{c.hours}-hour'
    # Quote the numbers only when they actually back the claim.
    if c.family in ('breakout','trend_breakout') and 'recent_high' in ctx and ctx['close']>ctx['recent_high']:
        text=(f"Bitcoin's price closed at {_usd(ctx['close'])}, above its highest price of the previous {c.fast} {span} periods "
              f"({_usd(ctx['recent_high'])}). This strategy treats breaking above a recent high as a sign the price may keep rising.")
        if 'long_average' in ctx:text+=f" The price was also above its long-term average ({_usd(ctx['long_average'])})."
        return text
    if c.family=='ema' and 'fast_average' in ctx and ctx['fast_average']>ctx['slow_average']:
        return (f"The short-term average price ({_usd(ctx['fast_average'])}) crossed above the long-term average ({_usd(ctx['slow_average'])}). "
                "This strategy treats that as a sign an upward trend may be starting.")
    if c.family=='rsi_pullback':
        return "After a dip, Bitcoin's momentum turned back up while the price stayed above its long-term average. This strategy treats that as a chance to buy the dip."
    return "The strategy's buy rule was met on the latest completed price period."

def exit_signal_reason(c,ctx):
    span=f'{c.hours}-hour'
    if c.family in ('breakout','trend_breakout') and 'recent_low' in ctx and ctx['close']<ctx['recent_low']:
        return (f"Bitcoin's price closed at {_usd(ctx['close'])}, below its lowest price of the previous {c.slow} {span} periods "
                f"({_usd(ctx['recent_low'])}). This strategy treats that as a sign the rise is over, so the bot sold.")
    if c.family=='ema':return "The short-term average price crossed back below the long-term average, a sign the upward trend may be over, so the bot sold."
    if c.family=='rsi_pullback':return "Momentum got high or the price fell below its long-term average, so the bot sold."
    return "The strategy's sell rule was met, so the bot sold."

class PaperDesk:
    def __init__(self,state_dir,selection=None,summary=None):
        self.dir=Path(state_dir);self.file=self.dir/'paper.json';self.lock=self.dir/'paper.lock'
        self.selection=Path(selection) if selection else ROOT/'state/selection.json'
        self.summary=Path(summary) if summary else None
        self.policy=Policy()
    def _new(self):
        return {'mode':'paper','enabled':False,'cash':self.policy.capital,'equity':self.policy.capital,
                'peak_equity':self.policy.capital,'position':None,'realized_pnl':0.,'fees_paid':0.,
                'last_signal_bar':None,'last_stop_bar':None,'last_checked_at':None,'price':None,
                'blocked':False,'block_reason':None,'status':'paused','events':[], 'equity_history':[],
                'periods':{},'exit_requested':False,'created_at':datetime.now(timezone.utc).isoformat(),
                'plan':{'capital':self.policy.capital,'risk_pct':self.policy.risk*100,'horizon_months':12},
                'strategy':None,'strategy_info':None,'trades':[]}
    def _read(self):
        if not self.file.exists(): return self._new()
        s=json.loads(self.file.read_text())
        if s.get('mode')!='paper':raise RuntimeError('Live execution is unsupported')
        if not all(math.isfinite(s[k]) for k in ['cash','equity','peak_equity']):raise RuntimeError('Corrupt paper account')
        return s
    def read(self):
        with locked(self.lock): return self._read()
    def control(self,action):
        if action not in ['start','pause','close']:raise ValueError('Unknown paper control')
        with locked(self.lock):
            s=self._read()
            if action=='start' and s['blocked']:raise ValueError('Risk stop is latched; review is required')
            s['enabled']=action=='start'
            if action=='close':s['exit_requested']=True
            s['status']='waiting_for_validation' if action=='start' else 'paused'
            self._event(s,'control',f'Paper account: {action}')
            atomic_json(self.file,s);return s
    def _validate(self,capital=None,risk_pct=None):
        if capital is not None and (not math.isfinite(capital) or not 100 <= capital <= 1000000): raise ValueError('Capital must be between 100 and 1,000,000 USDT')
        if risk_pct is not None and (not math.isfinite(risk_pct) or not .05 <= risk_pct <= .5): raise ValueError('Risk per trade must be between 0.05% and 0.50%')
    def _reset_balance(self,s,capital):
        s.update(cash=capital,equity=capital,peak_equity=capital,realized_pnl=0.,fees_paid=0.,periods={},equity_history=[],
                 last_signal_bar=None,last_stop_bar=None,exit_requested=False,trades=[])
    def configure(self, capital=None, risk_pct=None, horizon_months=None):
        with locked(self.lock):
            s=self._read()
            if s.get('position'): raise ValueError('Pause and close the paper position before changing the plan')
            self._validate(capital,risk_pct)
            plan=s.setdefault('plan',{'capital':self.policy.capital,'risk_pct':self.policy.risk*100,'horizon_months':12})
            if capital is not None:
                if capital!=plan.get('capital') or not s.get('trades'): self._reset_balance(s,capital)
                plan['capital']=capital
            if risk_pct is not None: plan['risk_pct']=risk_pct
            if horizon_months is not None:
                if not 1 <= horizon_months <= 120: raise ValueError('Investment horizon must be between 1 and 120 months')
                plan['horizon_months']=horizon_months
            self._event(s,'plan','Paper plan updated',plan=dict(plan));atomic_json(self.file,s);return s
    def setup(self,capital,risk_pct=None):
        """Start (or restart) practice trading: fresh balance, learning strategy on, bot enabled."""
        with locked(self.lock):
            s=self._read()
            if s.get('position'): raise ValueError('Sell the Bitcoin the bot owns before starting over')
            if s['blocked']: raise ValueError('Risk stop is latched; review is required')
            self._validate(capital,risk_pct)
            plan=s.setdefault('plan',{'capital':self.policy.capital,'risk_pct':self.policy.risk*100,'horizon_months':12})
            plan['capital']=capital
            if risk_pct is not None: plan['risk_pct']=risk_pct
            self._reset_balance(s,capital)
            _,info=learning_candidate(self.summary)
            s.update(strategy='learning',strategy_info=info,enabled=True,status='watching')
            self._event(s,'setup',f'Practice trading started with {capital:,.2f} USDT',plan=dict(plan),strategy=info['key'])
            atomic_json(self.file,s);return s
    def _event(self,s,kind,message,**extra):
        s['events'].append({'at':datetime.now(timezone.utc).isoformat(),'kind':kind,'message':message,**extra})
        # Retain the full paper audit trail; the API limits only the displayed slice.
    def _close(self,s,raw,reason,at,why=None):
        p=s['position'];px=raw*(1-self.policy.slippage);fee=p['qty']*px*self.policy.fee
        pnl=p['qty']*(px-p['entry'])-p['entry_fee']-fee
        s['cash']+=p['qty']*px-fee;s['fees_paid']+=fee;s['realized_pnl']+=pnl;s['position']=None
        self._event(s,'exit',f'Paper exit: {reason}',price=px,quantity=p['qty'],pnl=pnl,fill_time=at)
        code=EXIT_CODES.get(reason) or ('stop' if raw<=p['stop'] else 'target')
        trade=next((t for t in reversed(s.get('trades',[])) if t['status']=='open'),None)
        if trade:
            held=(pd.Timestamp(at)-pd.Timestamp(trade['opened_at'])).total_seconds()/3600
            trade.update(status='closed',closed_at=at,exit_market_price=raw,exit_price=px,exit_fee=fee,pnl=pnl,
                         pnl_pct=pnl/(trade['cost']+trade['entry_fee'])*100,exit_reason=code,
                         exit_why=why or EXIT_TEXT.get(code,'The bot sold.'),held_hours=max(0.,held))
    def tick(self,snap):
        with locked(self.lock):
            s=self._read();before=s['status'];p=self.policy
            if s.get('plan',{}).get('risk_pct') is not None: p=replace(p,risk=float(s['plan']['risk_pct'])/100)
            try:
                now=int(snap['server_ms']);price=float(snap['price']);bars=snap['bars']
                if not math.isfinite(price) or price<=0:raise ValueError('Invalid market price')
                if abs(now-int(snap['observed_ms']))>300000:raise ValueError('Clock mismatch or stale response')
                if not bars or now-bars[-1]['time']-HOUR>HOUR+90000:raise ValueError('Completed candles are stale')
                if bars[-1]['time']+HOUR>now:raise ValueError('Unfinished signal candle')
                if any(b['time']-a['time']!=HOUR for a,b in zip(bars,bars[1:])):raise ValueError('Recent market-data gap')
                if any(not all(math.isfinite(r[k]) for k in ['open','high','low','close']) or r['high']<max(r['open'],r['close']) or r['low']>min(r['open'],r['close']) for r in bars):raise ValueError('Invalid recent OHLC data')
                s['price']=price;s['last_checked_at']=utc(now)
                # Resting protective orders can be modelled only on FULL bars after the paper entry.
                if s['position']:
                    pos=s['position']
                    for b in bars:
                        if b['time']<=max(pos['opened_ms'],s['last_stop_bar'] or 0):continue
                        if b['low']<=pos['stop']:
                            self._close(s,min(b['open'],pos['stop']),'modelled resting stop',utc(b['time']));break
                        if b['high']>=pos['target']:
                            self._close(s,pos['target'],'modelled resting target',utc(b['time']));break
                    s['last_stop_bar']=bars[-1]['time']
                if s['position'] and (s['exit_requested'] or price<=s['position']['stop'] or price>=s['position']['target']):
                    self._close(s,price,'requested close' if s['exit_requested'] else 'observed protective exit',utc(now))
                s['exit_requested']=False
                equity=s['cash']+(s['position']['qty']*price if s['position'] else 0.)
                s['peak_equity']=max(s['peak_equity'],equity)
                ts=datetime.fromtimestamp(now/1000,timezone.utc)
                period_keys={'day':ts.strftime('%Y-%m-%d'),'week':f'{ts.isocalendar().year}-{ts.isocalendar().week}','month':ts.strftime('%Y-%m')}
                for k,key in period_keys.items():
                    if s['periods'].get(k,{}).get('key')!=key:s['periods'][k]={'key':key,'base':equity}
                changes={k:equity/v['base']-1 for k,v in s['periods'].items()}
                if equity/s['peak_equity']-1<=-p.max_drawdown:
                    s['blocked']=True;s['block_reason']='10% peak drawdown stop';s['enabled']=False
                if s['position'] and (s['blocked'] or changes['day']<-.03):self._close(s,price,'risk stop',utc(now))
                gates=not s['blocked'] and changes['day']>=-.03 and changes['week']>-.06 and changes['month']>-.10
                selection=json.loads(self.selection.read_text()) if self.selection.exists() else {'eligible':False}
                required={'positive_return','profit_factor_at_least_1_10','sufficient_trades','drawdown_below_10pct','no_risk_stop','validation_passed'}
                evidence=selection.get('gates',{})
                qualified=selection.get('eligible') is True and required.issubset(evidence) and all(evidence[k] is True for k in required)
                c=Candidate(**selection['candidate']) if qualified and selection.get('candidate') else None
                if c:s['strategy_info']={'key':c.key,'name':NAMES.get(c.family,c.family),'learning':False,**asdict(c)}
                elif s.get('strategy')=='learning':
                    # Opt-in practice trading with the best tested (but unqualified) strategy; clearly labelled as such.
                    c,s['strategy_info']=learning_candidate(self.summary)
                if c:
                    frame=pd.DataFrame(bars);frame.index=pd.to_datetime(frame.time,unit='ms',utc=True)
                    if c.hours>1:
                        count=frame.close.resample(f'{c.hours}h').count()
                        frame=frame.resample(f'{c.hours}h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
                        frame=frame.loc[count==c.hours]
                    frame['gap']=False
                    if len(frame)<max(201,c.slow+2,c.fast+2):raise ValueError('Insufficient indicator warm-up')
                    sig=signals(frame,c).iloc[-1];bar=int(frame.index[-1].timestamp()*1000)
                    if s['last_signal_bar']!=bar:
                        if s['position'] and bool(sig['leave']):
                            self._close(s,price,'completed-bar signal',utc(now),why=exit_signal_reason(c,signal_context(frame,c)))
                        if not s['position'] and s['enabled'] and gates and bool(sig['entry']) and math.isfinite(sig['atr']):
                            entry=price*(1+p.slippage);distance=float(sig['atr'])*c.stop_atr
                            qty=position_qty(s['cash'],entry,distance,p)
                            halved=changes['day']<=-.02 or changes['week']<=-.05
                            if halved:qty=math.floor(qty*.5/p.qty_step)*p.qty_step
                            if qty and qty*entry>=p.min_notional:
                                fee=qty*entry*p.fee;s['cash']-=qty*entry+fee;s['fees_paid']+=fee
                                s['position']={'qty':qty,'entry':entry,'entry_fee':fee,'stop':entry-distance,
                                               'target':entry+distance*c.reward_r,'opened_ms':now,'candidate':c.key}
                                self._event(s,'entry','Paper entry at observed price',price=entry,quantity=qty,signal_bar=utc(bar))
                                ctx=signal_context(frame,c)
                                s.setdefault('trades',[]).append({
                                    'id':f"T{len(s.get('trades',[]))+1}",'status':'open','strategy':s['strategy_info'],
                                    'opened_at':utc(now),'signal_bar':utc(bar),'bar_hours':c.hours,'market_price':price,
                                    'entry_price':entry,'qty':qty,'cost':qty*entry,'entry_fee':fee,'stop':entry-distance,
                                    'target':entry+distance*c.reward_r,'atr':float(sig['atr']),'stop_atr':c.stop_atr,'reward_r':c.reward_r,
                                    'risk_pct':p.risk*100,'planned_loss':qty*distance+fee+qty*(entry-distance)*p.fee,
                                    'account_before':equity,'size_halved':halved,'context':ctx,'why':entry_reason(c,ctx)})
                                s['trades']=s['trades'][-500:]
                        s['last_signal_bar']=bar
                s['equity']=s['cash']+(s['position']['qty']*price if s['position'] else 0.)
                s['status']='risk_stopped' if s['blocked'] else ('paused' if not s['enabled'] else ('waiting_for_validation' if c is None else ('holding' if s['position'] else 'watching')))
                point={'time':utc(now),'equity':s['equity']}
                if not s['equity_history'] or s['equity_history'][-1]['time'][:13]!=point['time'][:13]:s['equity_history'].append(point)
                else:s['equity_history'][-1]=point
                s['equity_history']=s['equity_history'][-3000:]
                s.pop('error',None)
            except (ValueError,KeyError,TypeError,IndexError) as e:
                s['status']='data_unavailable';s['error']=str(e)
            if before!=s['status']:self._event(s,'status',s['status'].replace('_',' '))
            atomic_json(self.file,s);return s

def cycle_all():
    base=ROOT/'state/accounts';base.mkdir(parents=True,exist_ok=True)
    accounts=list(base.glob('*/paper.json'))
    if not accounts:return {'accounts':0}
    data=snapshot()
    return {'accounts':len(accounts),'states':{x.parent.name:PaperDesk(x.parent).tick(data)['status'] for x in accounts}}

if __name__=='__main__':print(json.dumps(cycle_all()))
