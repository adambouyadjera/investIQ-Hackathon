import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
import pandas as pd
from desk.paper import PaperDesk,atomic_json
from desk.research import Candidate
from desk.market import HOUR

class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.selection=self.root/'selection.json'
        atomic_json(self.selection,{'eligible':False,'candidate':None});self.desk=PaperDesk(self.root/'account',self.selection)
        start=int(pd.Timestamp('2026-01-01T00:00:00Z').timestamp()*1000)
        self.bars=[{'time':start+i*HOUR,'open':100.,'high':100.1,'low':99.9,'close':100.,'volume':10.} for i in range(250)]
        now=self.bars[-1]['time']+HOUR+60_000
        self.snap={'server_ms':now,'observed_ms':now,'price':100.,'bars':self.bars}
    def tearDown(self):self.tmp.cleanup()
    def approve_for_test(self):
        atomic_json(self.selection,{'eligible':True,'candidate':asdict(Candidate('ema',1,20,50)),'gates':{k:True for k in ['positive_return','profit_factor_at_least_1_10','sufficient_trades','drawdown_below_10pct','no_risk_stop','validation_passed']}})
    def fake_signal(self,df,c):
        return pd.DataFrame({'entry':True,'leave':False,'atr':1.},index=df.index)
    def test_cash_only_without_qualified_strategy(self):
        self.desk.control('start');r=self.desk.tick(self.snap)
        self.assertEqual(r['equity'],10000);self.assertIsNone(r['position']);self.assertEqual(r['status'],'waiting_for_validation')
    def test_qualifying_signal_only_once_and_at_observed_price(self):
        self.approve_for_test();self.desk.control('start')
        with patch('desk.paper.signals',self.fake_signal):
            a=self.desk.tick(self.snap);b=self.desk.tick(self.snap)
        self.assertIsNotNone(a['position']);self.assertEqual(a['cash'],b['cash'])
        self.assertEqual(len([e for e in b['events'] if e['kind']=='entry']),1)
        self.assertAlmostEqual(a['position']['entry'],100.05)
    def test_stale_data_cannot_open_position(self):
        self.approve_for_test();self.desk.control('start');self.snap['observed_ms']-=600000
        r=self.desk.tick(self.snap);self.assertEqual(r['status'],'data_unavailable');self.assertIsNone(r['position'])
    def test_gap_data_cannot_open_position(self):
        self.bars.pop(-5);self.approve_for_test();self.desk.control('start')
        r=self.desk.tick(self.snap);self.assertEqual(r['status'],'data_unavailable');self.assertIsNone(r['position'])
    def test_pause_prevents_new_entries(self):
        self.approve_for_test();self.desk.control('pause')
        with patch('desk.paper.signals',self.fake_signal):r=self.desk.tick(self.snap)
        self.assertIsNone(r['position'])
    def test_restart_keeps_balance_and_position(self):
        self.approve_for_test();self.desk.control('start')
        with patch('desk.paper.signals',self.fake_signal):a=self.desk.tick(self.snap)
        b=PaperDesk(self.root/'account',self.selection).read();self.assertEqual(a,b)
    def test_simulated_exit_reconciles_cash(self):
        self.approve_for_test();self.desk.control('start')
        with patch('desk.paper.signals',self.fake_signal):self.desk.tick(self.snap)
        self.desk.control('close');self.snap['price']=101.
        with patch('desk.paper.signals',self.fake_signal):r=self.desk.tick(self.snap)
        self.assertIsNone(r['position']);self.assertAlmostEqual(r['cash']-10000,r['realized_pnl']);self.assertFalse(r['enabled'])
    def test_account_isolation(self):
        self.desk.control('start');other=PaperDesk(self.root/'other',self.selection)
        self.assertFalse(other.read()['enabled']);self.assertTrue(self.desk.read()['enabled'])
    def test_no_live_mode(self):
        state=self.desk.read();state['mode']='live';atomic_json(self.desk.file,state)
        with self.assertRaises(RuntimeError):self.desk.read()
    def test_block_latch_cannot_be_started(self):
        state=self.desk.read();state['blocked']=True;atomic_json(self.desk.file,state)
        with self.assertRaises(ValueError):self.desk.control('start')
    def test_risk_stop_closes_and_blocks(self):
        self.approve_for_test();self.desk.control('start')
        with patch('desk.paper.signals',self.fake_signal):self.desk.tick(self.snap)
        self.snap['price']=1.
        with patch('desk.paper.signals',self.fake_signal):r=self.desk.tick(self.snap)
        self.assertIsNone(r['position']);self.assertTrue(r['blocked']);self.assertFalse(r['enabled'])
    def test_eligibility_flag_without_evidence_cannot_trade(self):
        atomic_json(self.selection,{'eligible':True,'candidate':asdict(Candidate('ema',1,20,50))})
        self.desk.control('start')
        with patch('desk.paper.signals',self.fake_signal):r=self.desk.tick(self.snap)
        self.assertIsNone(r['position']);self.assertEqual(r['status'],'waiting_for_validation')
    def test_invalid_price_cannot_trade(self):
        self.desk.control('start');self.snap['price']=float('nan');r=self.desk.tick(self.snap)
        self.assertEqual(r['status'],'data_unavailable');self.assertEqual(r['cash'],10000)
if __name__=='__main__':unittest.main()
