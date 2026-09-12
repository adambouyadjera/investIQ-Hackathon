import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from desk.research import Candidate,Policy,signals,simulate,position_qty
from desk.market import normalize,HOUR

class ResearchTests(unittest.TestCase):
    def bars(self,n=6):
        df=pd.DataFrame({'open':np.full(n,100.),'high':np.full(n,101.),'low':np.full(n,99.),'close':np.full(n,100.),'volume':np.ones(n),'gap':np.zeros(n,dtype=bool)},index=pd.date_range('2024-01-01',periods=n,freq='h',tz='UTC'))
        return df
    def signal(self,df):
        s=pd.DataFrame({'entry':False,'leave':False,'atr':1.},index=df.index);s.iloc[0,0]=True;return s
    def run_sim(self,df,s,p=None):
        return simulate(df,Candidate('ema',1,2,3),df.index[0],df.index[-1]+pd.Timedelta(hours=1),p or Policy(),s)
    def test_signal_enters_next_open(self):
        d=self.bars();d.iloc[1,d.columns.get_loc('open')]=100.5
        r=self.run_sim(d,self.signal(d));t=r['trades'][0]
        self.assertEqual(t['entry_time'],d.index[1].isoformat());self.assertAlmostEqual(t['entry_price'],100.5*1.0005)
    def test_fee_accounting_reconciles(self):
        d=self.bars();r=self.run_sim(d,self.signal(d))
        self.assertAlmostEqual(sum(t['pnl'] for t in r['trades']),r['metrics']['final_equity']-10000)
        self.assertGreater(r['metrics']['fees'],0)
    def test_stop_first_when_both_hit(self):
        d=self.bars();d.loc[d.index[1],['high','low']]=[110.,90.]
        r=self.run_sim(d,self.signal(d));self.assertEqual(r['trades'][0]['reason'],'stop');self.assertLess(r['trades'][0]['pnl'],0)
    def test_gap_stop_fills_worse_open(self):
        d=self.bars();d.loc[d.index[2],['open','high','low','close']]=[90.,91.,89.,90.]
        r=self.run_sim(d,self.signal(d));t=r['trades'][0]
        self.assertEqual(t['reason'],'gap_stop');self.assertAlmostEqual(t['exit_price'],90*.9995)
    def test_risk_size_includes_costs(self):
        p=Policy();q=position_qty(10000,100000,2000,p)
        self.assertLessEqual(q*(2000+100000*(2*p.fee+2*p.slippage)),50)
        self.assertLessEqual(q*100000*(1+p.fee),5000)
        self.assertLess(q,1)
    def test_nonpositive_stop_cannot_be_sized(self):
        self.assertEqual(position_qty(10000,100,110,Policy()),0)
    def test_drawdown_latches_and_stops_entries(self):
        d=self.bars();d.loc[d.index[2],['open','high','low','close']]=[1.,1.,1.,1.]
        s=self.signal(d);s.loc[d.index[3],'entry']=True
        r=self.run_sim(d,s,replace(Policy(),max_drawdown=.001));self.assertTrue(r['metrics']['halted']);self.assertEqual(len(r['trades']),1)
    def test_higher_costs_reduce_fixed_trade_return(self):
        d=self.bars();s=self.signal(d)
        a=self.run_sim(d,s);b=self.run_sim(d,s,replace(Policy(),fee=.002,slippage=.001))
        self.assertLess(b['metrics']['net_return'],a['metrics']['net_return'])
    def test_future_prices_do_not_change_past_signals(self):
        d=self.bars(600);d['close']=100+np.sin(np.arange(600)/7)*10;d['open']=d.close;d['high']=d.close+1;d['low']=d.close-1
        for family,a,b in [('ema',10,50),('breakout',20,10),('rsi_pullback',14,30)]:
            c=Candidate(family,1,a,b);orig=signals(d,c)
            changed=d.copy();changed.iloc[400:,changed.columns.get_loc('close')]*=2
            pd.testing.assert_frame_equal(orig.iloc[:400],signals(changed,c).iloc[:400])
    def test_window_excludes_later_trades(self):
        d=self.bars();s=self.signal(d);s.iloc[4,0]=True
        r=simulate(d,Candidate('ema',1,2,3),d.index[0],d.index[3],Policy(),s)
        self.assertEqual(len(r['trades']),1);self.assertEqual(r['metrics']['bars'],3)
    def test_gaps_clear_indicator_warmup(self):
        d=self.bars(500);d.iloc[300,d.columns.get_loc('gap')]=True
        s=signals(d,Candidate('ema',1,20,50));self.assertFalse(s.iloc[300:350].entry.any());self.assertTrue(np.isnan(s.iloc[300].atr))
    def test_unfinished_bar_removed(self):
        row=[0,100,101,99,100,1,HOUR-1]
        self.assertEqual(normalize([row],HOUR-1),[]);self.assertEqual(len(normalize([row],HOUR)),1)
    def test_bad_ohlc_rejected(self):
        with self.assertRaises(ValueError):normalize([[0,100,90,99,100,1,HOUR-1]],HOUR)
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):normalize([[0,100,101,99,float('nan'),1,HOUR-1]],HOUR)
    def test_duplicate_rejected(self):
        row=[0,100,101,99,100,1,HOUR-1]
        with self.assertRaises(ValueError):normalize([row,row],HOUR)

if __name__=='__main__': unittest.main()
