import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from desk.paper import PaperDesk,atomic_json,learning_candidate
from desk.market import HOUR

SUMMARY={'validations':[
    {'name':'Local ridge model','candidate':{'family':'ridge','hours':4,'fast':100,'slow':30,'stop_atr':3.0,'reward_r':3.0},'metrics':{'net_return':.5,'trades':9},'gates':{'positive_return':True}},
    {'name':'Channel breakout','candidate':{'family':'breakout','hours':4,'fast':40,'slow':20,'stop_atr':3.0,'reward_r':2.0},'metrics':{'net_return':.009,'trades':24},'gates':{'positive_return':True,'positive_under_double_costs':False}},
    {'name':'EMA trend crossover','candidate':{'family':'ema','hours':1,'fast':50,'slow':200,'stop_atr':3.0,'reward_r':2.0},'metrics':{'net_return':-.02,'trades':36},'gates':{'positive_return':False}}]}

class LearningTradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        atomic_json(root/'selection.json',{'eligible':False,'candidate':None});atomic_json(root/'summary.json',SUMMARY)
        self.summary=root/'summary.json';self.desk=PaperDesk(root/'account',root/'selection.json',self.summary)
        start=int(pd.Timestamp('2026-01-01T00:00:00Z').timestamp()*1000)
        bars=[{'time':start+i*HOUR,'open':100.,'high':100.1,'low':99.9,'close':100.,'volume':10.} for i in range(1000)]
        now=bars[-1]['time']+HOUR+60_000
        self.snap={'server_ms':now,'observed_ms':now,'price':100.,'bars':bars}
    def tearDown(self):self.tmp.cleanup()
    def signal(self,entry=True,leave=False):
        return lambda df,c:pd.DataFrame({'entry':entry,'leave':leave,'atr':1.},index=df.index)
    def test_learning_candidate_skips_unsupported_families(self):
        c,info=learning_candidate(self.summary)
        self.assertEqual(c.key,'breakout_4h_40_20_atr3');self.assertTrue(info['learning'])
        self.assertIn('positive_under_double_costs',info['failed_checks'])
    def test_no_trades_without_setup(self):
        self.desk.control('start')
        with patch('desk.paper.signals',self.signal()):r=self.desk.tick(self.snap)
        self.assertEqual(r['status'],'waiting_for_validation');self.assertEqual(r['trades'],[])
    def test_setup_resets_balance_and_trades_with_explanation(self):
        s=self.desk.setup(2500,0.25)
        self.assertEqual((s['cash'],s['plan']['capital'],s['plan']['risk_pct']),(2500,2500,0.25));self.assertTrue(s['enabled'])
        with patch('desk.paper.signals',self.signal()):r=self.desk.tick(self.snap)
        self.assertEqual(r['status'],'holding');self.assertEqual(len(r['trades']),1)
        t=r['trades'][0]
        self.assertEqual(t['status'],'open');self.assertTrue(t['strategy']['learning'])
        self.assertTrue(t['why'])  # flat fixture prices: wording guard picks the generic sentence (see test below)
        self.assertAlmostEqual(t['entry_price'],100.05);self.assertAlmostEqual(t['stop'],100.05-3.)
        self.assertAlmostEqual(t['cost']+t['entry_fee'],2500-r['cash'])
        self.assertLessEqual(t['cost'],2500*.5)
    def test_explanation_never_quotes_numbers_that_contradict_it(self):
        from desk.paper import entry_reason,exit_signal_reason
        c,_=learning_candidate(self.summary)
        self.assertNotIn('above its highest',entry_reason(c,{'close':77114.99,'recent_high':80559.99,'recent_low':70000.}))
        self.assertIn('above its highest',entry_reason(c,{'close':81000.,'recent_high':80559.99,'recent_low':70000.}))
        self.assertNotIn('below its lowest',exit_signal_reason(c,{'close':75000.,'recent_high':80000.,'recent_low':70000.}))
    def test_manual_sell_closes_trade_and_reconciles(self):
        self.desk.setup(10000)
        with patch('desk.paper.signals',self.signal()):self.desk.tick(self.snap)
        self.desk.control('close');self.snap['price']=101.
        with patch('desk.paper.signals',self.signal(entry=False)):r=self.desk.tick(self.snap)
        t=r['trades'][0]
        self.assertEqual((t['status'],t['exit_reason']),('closed','manual'))
        self.assertAlmostEqual(t['pnl'],r['realized_pnl']);self.assertAlmostEqual(r['cash']-10000,t['pnl'])
        self.assertIn('You asked',t['exit_why'])
    def test_loss_limit_sell_is_explained(self):
        self.desk.setup(10000)
        with patch('desk.paper.signals',self.signal()):self.desk.tick(self.snap)
        self.snap['price']=96.
        with patch('desk.paper.signals',self.signal(entry=False)):r=self.desk.tick(self.snap)
        t=r['trades'][0];self.assertEqual(t['exit_reason'],'stop');self.assertLess(t['pnl'],0);self.assertIn('loss limit',t['exit_why'])
    def test_setup_refused_while_holding(self):
        self.desk.setup(10000)
        with patch('desk.paper.signals',self.signal()):self.desk.tick(self.snap)
        with self.assertRaises(ValueError):self.desk.setup(5000)
    def test_changing_amount_twice_resets_each_time(self):
        self.desk.configure(capital=5000);s=self.desk.configure(capital=8000)
        self.assertEqual((s['cash'],s['equity'],s['plan']['capital']),(8000,8000,8000))

if __name__=='__main__':unittest.main()
