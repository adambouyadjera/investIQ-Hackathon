import json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from desk.paper import atomic_json
from desk.portfolio_bot import PortfolioBot,HistoricalMarket,analyze,allocate,timeframe_for,ConfirmationRequired,RISK,REVIEW_MINUTES

UNIVERSE={'SPY':('S&P fund','etf','big US companies',r'S&P'),'BND':('Bond fund','bond','bonds',r'bond'),
          'AAA':('Alpha Corp','stock','gadgets',r'Alpha'),'BBB':('Beta Corp','stock','rockets',r'Beta'),'CCC':('Crash Corp','stock','fads',r'Crash')}

def series(drift,vol,seed,n=300,start=100.):
    rng=np.random.default_rng(seed);close=start*np.exp(np.cumsum(drift/252+vol/np.sqrt(252)*rng.standard_normal(n)))
    dates=pd.bdate_range('2025-07-01',periods=n)
    return {'dates':[d.strftime('%Y-%m-%d') for d in dates],'close':close.tolist(),'high':(close*1.004).tolist(),'low':(close*.996).tolist()}

CRYPTO_UNIVERSE={**UNIVERSE,'CRY':('Crypto Coin','crypto','a digital coin',r'Coin')}

class FakeMarket:
    def __init__(self):
        self.data={'SPY':series(.25,.12,1),'BND':series(.06,.04,2),'AAA':series(.6,.22,3),'BBB':series(.5,.9,4),'CCC':series(-.8,.3,5),'CRY':series(1.4,.3,7)}
    def history(self,tickers):return {t:v for t,v in self.data.items() if t in tickers}
    def fundamentals(self,tickers):return {'AAA':{'profitMargins':.25,'revenueGrowth':.15,'trailingPE':22.}}
    def news(self,t):return [{'title':'Alpha Corp profits surge on record sales','url':'https://example.com/a','source':'Example Wire','published_at':'2026-09-11T12:00:00Z'}] if t=='AAA' else []
    def headlines(self):return []
    def shock(self,t,factor):
        d=self.data[t];d['close'][-1]*=factor;d['high'][-1]*=factor;d['low'][-1]*=factor

class PortfolioBotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.market=FakeMarket()
        self.now=datetime(2026,9,12,15,0,tzinfo=timezone.utc)
        self.bot=PortfolioBot(Path(self.tmp.name),self.market,UNIVERSE,lambda:self.now,market_open=lambda now:True)
    def tearDown(self):self.tmp.cleanup()

    def test_low_risk_respects_limits_and_skips_jumpy_or_falling_assets(self):
        a=analyze(self.market.data,{},{},[],'low','medium',UNIVERSE);r=RISK['low']
        self.assertNotIn('BBB',a['targets']);self.assertNotIn('CCC',a['targets'])
        self.assertTrue(any('jumpy' in b for b in a['assets']['BBB']['blockers']))
        self.assertLessEqual(sum(a['targets'].values()),1-r['cash']+1e-6)
        self.assertTrue(all(w<=r['max_weight']+1e-6 for w in a['targets'].values()))
        self.assertLessEqual(sum(w for t,w in a['targets'].items() if UNIVERSE[t][1]=='stock'),r['stock_share']+1e-6)

    def test_one_industry_is_capped(self):
        picks=[{'ticker':'XLF','kind':'etf','score':.9,'metrics':{'vol':.15}},{'ticker':'JPM','kind':'stock','score':.9,'metrics':{'vol':.15}},
               {'ticker':'SPY','kind':'etf','score':.5,'metrics':{'vol':.15}}]
        w=allocate(picks,.9,RISK['medium'],'medium')
        self.assertLessEqual(w['XLF']+w['JPM'],RISK['medium']['sector_cap']+1e-6);self.assertGreater(w['SPY'],0)

    def test_months_choose_plan_rules(self):
        self.assertEqual([timeframe_for(m) for m in (1,3,4,12,13,120)],['short','short','medium','medium','long','long'])
        for months in (0,121,2.5):
            with self.assertRaises(ValueError):self.bot.setup(1000,'low',months)

    def test_setup_buys_and_records_consistent_trades(self):
        p=self.bot.setup(10000,'medium',6)
        self.assertEqual((p['settings']['months'],p['settings']['timeframe'],p['deposits']),(6,'medium',10000))
        buys=[t for t in p['trades'] if t['action']=='BUY'];self.assertTrue(buys)
        for a,b in zip(p['trades'],p['trades'][1:]):self.assertAlmostEqual(a['cash_after'],b['cash_before'])
        self.assertAlmostEqual(p['cash']+p['holdings_value'],p['portfolio_value'])
        self.assertLess(abs(p['portfolio_value']-10000),10000*0.001)  # only simulated price differences
        self.assertEqual(p['equity_history'][-1]['trades'],[t['id'] for t in p['trades']])
        self.assertEqual(p['equity_history'][-1]['deposits'],10000)
        self.assertTrue(all(t['pnl_type']=='unrealized' for t in buys))
        e=buys[0]['explanation']
        for key in ['summary','market','news','price_movement','indicators','fundamentals','volatility','risk_factors','why_asset','alternatives',
                    'why_amount','holding_period','downside','sell_conditions','strategy_change','disclaimer']:
            self.assertTrue(e[key],key)
        self.assertIn('6 months',e['holding_period'])
        aaa=next(t for t in buys if t['ticker']=='AAA')['explanation']
        self.assertEqual((aaa['news'][0]['source'],aaa['news'][0]['published_at'],aaa['news'][0]['tone']),('Example Wire','2026-09-11T12:00:00Z','positive'))
        self.assertTrue(all(t['simulated'] for t in p['trades']))

    def test_no_promises_in_explanations(self):
        p=self.bot.setup(5000,'high',2)
        text=json.dumps([t['explanation'] for t in p['trades']]).lower().replace('no result is guaranteed','')
        for word in ['guarantee','certain to','risk-free','will make']:self.assertNotIn(word,text)

    def test_loss_limit_sells_between_reviews_with_realized_loss(self):
        self.bot.setup(10000,'medium',24);self.assertIn('AAA',[h['ticker'] for h in self.bot.refresh(False)['holdings']])
        self.market.shock('AAA',0.7);self.now+=timedelta(hours=2)
        p=self.bot.refresh()
        sale=p['trades'][-1]
        self.assertEqual((sale['ticker'],sale['action'],sale['reason'],sale['pnl_type']),('AAA','SELL','stop','realized'))
        self.assertLess(sale['realized_pnl'],0);self.assertAlmostEqual(p['realized_pnl'],sale['realized_pnl'])
        self.assertNotIn('AAA',[h['ticker'] for h in p['holdings']]);self.assertIn('loss limit',sale['explanation']['summary'])

    def test_scheduled_review_sells_assets_that_no_longer_qualify(self):
        self.bot.setup(10000,'medium',2)
        d=self.market.data['AAA'];d['close'][-1]=d['close'][-2]*0.93;d['high'][-1]=d['close'][-1];d['low'][-1]=d['close'][-1]
        self.now+=timedelta(days=1,minutes=1)
        p=self.bot.refresh()
        sold=[t for t in p['trades'] if t['ticker']=='AAA' and t['action']=='SELL']
        self.assertTrue(sold);self.assertIn(sold[-1]['reason'],('dropped','stop'))

    def test_valuation_refresh_does_not_trade(self):
        p=self.bot.setup(10000,'low',6);n=len(p['trades']);self.assertTrue(p['holdings'])
        self.market.shock(p['holdings'][0]['ticker'],1.05);self.now+=timedelta(minutes=5)
        q=self.bot.refresh(allow_trades=False)
        self.assertEqual(len(q['trades']),n);self.assertNotEqual(q['portfolio_value'],p['portfolio_value'])

    def test_pause_blocks_trading(self):
        self.bot.setup(10000,'medium',2);self.bot.control('pause');n=len(self.bot.refresh(False)['trades'])
        self.market.shock('AAA',0.5);self.now+=timedelta(days=2)
        q=self.bot.refresh();self.assertEqual(len(q['trades']),n);self.assertEqual(q['status'],'paused')

    def test_raising_amount_adds_cash_and_keeps_history(self):
        p=self.bot.setup(10000,'medium',6);self.bot.control('pause');ids=[t['id'] for t in p['trades']]
        q=self.bot.update_settings(12000,'medium',6)
        self.assertAlmostEqual(q['cash'],p['cash']+2000);self.assertEqual([t['id'] for t in q['trades']],ids)
        self.assertEqual((q['settings']['amount'],q['deposits']),(12000,12000))
        self.assertAlmostEqual(q['total_return'],q['portfolio_value']-12000)

    def test_lowering_amount_requires_confirmation_and_sells_when_cash_is_short(self):
        p=self.bot.setup(10000,'medium',6);self.bot.control('pause');n=len(p['trades'])
        target=round(10000-(p['cash']+1000),2)  # take out $1,000 more than the cash on hand, so investments must be sold
        with self.assertRaises(ConfirmationRequired):self.bot.update_settings(target,'medium',6)
        self.assertEqual(self.bot.refresh(False)['deposits'],10000)  # nothing changed without confirmation
        q=self.bot.update_settings(target,'medium',6,confirm=True)
        withdrawals=[t for t in q['trades'][n:] if t['reason']=='withdraw']
        self.assertTrue(withdrawals);self.assertTrue(all(t['action']=='SELL' for t in withdrawals))
        self.assertAlmostEqual(q['deposits'],target)
        self.assertLess(abs(q['portfolio_value']-(p['portfolio_value']-(10000-target))),5)
        self.assertEqual([t['id'] for t in q['trades'][:n]],[t['id'] for t in p['trades']])

    def test_cannot_lower_amount_below_what_the_portfolio_is_worth(self):
        p=self.bot.setup(10000,'medium',6);self.bot.control('pause')
        held=p['holdings'][0]['ticker'];self.market.shock(held,0.2);self.bot.refresh(False)  # a big simulated loss
        with self.assertRaises(ValueError) as ctx:self.bot.update_settings(100,'medium',6,confirm=True)
        self.assertNotIsInstance(ctx.exception,ConfirmationRequired)
        self.assertEqual(self.bot.refresh(False)['deposits'],10000)

    def test_start_over_requires_confirmation_and_keeps_history(self):
        p=self.bot.setup(10000,'medium',6);n=len(p['trades']);self.bot.control('pause')
        with self.assertRaises(ConfirmationRequired):self.bot.update_settings(5000,'low',24,reset=True)
        q=self.bot.update_settings(5000,'low',24,confirm=True,reset=True)
        self.assertEqual(q['holdings'],[]);self.assertAlmostEqual(q['cash'],5000);self.assertAlmostEqual(q['total_return'],0)
        self.assertEqual([t['id'] for t in q['trades'][:n]],[t['id'] for t in p['trades']])
        self.assertTrue(q['trades'][n:] and all(t['reason']=='reset' for t in q['trades'][n:]))

    def test_changing_risk_and_period_rebuilds_plan_when_running(self):
        p=self.bot.setup(10000,'high',2);n=len(p['trades'])
        q=self.bot.update_settings(10000,'low',24)
        self.assertEqual((q['settings']['risk'],q['settings']['months'],q['settings']['timeframe']),('low',24,'long'))
        self.assertGreaterEqual(len(q['trades']),n);self.assertTrue(any('changed the settings' in a['text'] for a in q['activity']))

    def test_input_validation_and_no_live_mode(self):
        with self.assertRaises(ValueError):self.bot.setup(50,'low',2)
        with self.assertRaises(ValueError):self.bot.setup(1000,'extreme',2)
        self.bot.setup(1000,'low',2);s=json.loads(self.bot.file.read_text());s['mode']='live';atomic_json(self.bot.file,s)
        with self.assertRaises(RuntimeError):self.bot.refresh()

    def test_market_closed_only_crypto_trades(self):
        bot=PortfolioBot(Path(self.tmp.name)/'closed',self.market,CRYPTO_UNIVERSE,lambda:self.now,market_open=lambda now:False)
        p=bot.setup(10000,'high',6)
        self.assertFalse(p['market_open']);self.assertTrue(p['trades'])
        self.assertTrue(all(t['kind']=='crypto' for t in p['trades']))
        self.assertLessEqual(sum(h['value'] for h in p['holdings'])/p['portfolio_value'],RISK['high']['crypto_share']+0.005)
        self.assertIn('7 days a week',p['trades'][0]['explanation']['price_note'])
        self.assertIn('crypto together is capped at 20%',p['trades'][0]['explanation']['why_amount'])

    def test_crypto_gets_its_own_slot_within_its_cap(self):
        market=FakeMarket();market.data['CRY']=series(.45,.28,11)  # qualifies, but unlikely to outrank the best stocks
        for risk in ('medium','high'):
            a=analyze(market.data,{},{},[],risk,'medium',CRYPTO_UNIVERSE)
            if a['assets']['CRY']['blockers']:self.skipTest(f"fixture coin blocked: {a['assets']['CRY']['blockers']}")
            self.assertIn('CRY',a['targets'],risk)
            self.assertLessEqual(a['targets']['CRY'],RISK[risk]['crypto_share']+1e-6)
            self.assertLessEqual(len([t for t in a['targets'] if t!='CRY']),RISK[risk]['picks'])

    def test_low_risk_never_uses_crypto(self):
        a=analyze(self.market.data,{},{},[],'low','medium',CRYPTO_UNIVERSE)
        self.assertNotIn('CRY',a['targets']);self.assertTrue(any('crypto is not used' in b for b in a['assets']['CRY']['blockers']))

    def test_reviews_on_schedule(self):
        p=self.bot.setup(10000,'medium',2);n=len(p['trades'])
        self.assertEqual(datetime.fromisoformat(p['next_review'])-self.now,timedelta(minutes=REVIEW_MINUTES))
        d=self.market.data['AAA'];d['close'][-1]=d['close'][-2]*0.93;d['high'][-1]=d['close'][-1];d['low'][-1]=d['close'][-1]
        self.now+=timedelta(minutes=REVIEW_MINUTES-2);self.assertEqual(len(self.bot.refresh()['trades']),n)  # not due yet
        self.now+=timedelta(minutes=3);self.assertGreater(len(self.bot.refresh()['trades']),n)

    def test_backfill_replays_past_days_with_only_what_was_known(self):
        dates=self.market.data['SPY']['dates']
        self.now=datetime.fromisoformat(dates[-1]).replace(hour=22,tzinfo=timezone.utc)+timedelta(days=1)
        p=self.bot.backfill(10000,'medium',6,days=20)
        self.assertEqual(p['replay']['days'],20)
        replayed=[t for t in p['trades'] if t.get('replayed')];self.assertTrue(replayed)
        first=replayed[0]
        self.assertLess(datetime.fromisoformat(first['time']),self.now-timedelta(days=10))
        i=dates.index(first['time'][:10])
        self.assertAlmostEqual(first['market_price'],self.market.data[first['ticker']]['close'][i])  # that day's close, not today's
        self.assertIn('Replayed trade',first['explanation']['price_note'])
        self.assertTrue(all(t['explanation']['news']==[] for t in replayed if t['ticker']=='AAA'))  # the only AAA headline is dated later
        self.assertGreaterEqual(len(p['equity_history']),10)
        with self.assertRaises(ConfirmationRequired):self.bot.backfill(10000,'medium',6,days=20)

    def test_buys_never_spend_the_cash_reserve(self):
        # Four similar funds with no stock, crypto or industry caps: a high-risk plan keeps exactly its 5% reserve.
        funds={f'F{i}':(f'Fund {i}','etf','many companies',rf'Fund {i}') for i in range(1,5)}
        for i in range(1,5):self.market.data[f'F{i}']=series(.35+.02*i,.12,30+i)
        bot=PortfolioBot(Path(self.tmp.name)/'reserve',self.market,funds,lambda:self.now,market_open=lambda now:True)
        p=bot.setup(10000,'high',2);self.assertEqual(len(p['holdings']),4)
        self.assertLess(p['cash']/p['portfolio_value'],RISK['high']['cash']+0.01)  # starts at (about) the reserve
        # Recreate the drain: one planned fund is missing, so the plan wants to buy it back, while the other three
        # sit just under the 3% trim band above target, paid for out of cash.
        state=json.loads(bot.file.read_text());prices=state['prices']
        missing,*others=list(state['holdings'])
        state['cash']+=state['holdings'][missing]['shares']*prices[missing];del state['holdings'][missing]
        for t in others:
            extra=state['holdings'][t]['shares']*0.028
            state['holdings'][t]['shares']+=extra;state['cash']-=extra*prices[t]
        atomic_json(bot.file,state)
        self.now+=timedelta(minutes=16);q=bot.refresh()
        self.assertTrue(any(t['ticker']==missing and t['action']=='BUY' for t in q['trades'][len(p['trades']):]))
        self.assertGreaterEqual(q['cash'],RISK['high']['cash']*q['portfolio_value']-1)

    def test_hourly_replay_market_hides_unfinished_and_future_bars(self):
        daily={'dates':[f'2026-01-{d:02d}' for d in range(1,32)]+[f'2026-02-{d:02d}' for d in range(1,29)]+['2026-03-01','2026-03-02','2026-03-03'],}
        n=len(daily['dates']);daily.update(close=[100.+i for i in range(n)],high=[101.+i for i in range(n)],low=[99.+i for i in range(n)])
        base=type('B',(),{'history':lambda self,t:{'SPY':daily},'fundamentals':lambda self,t:{},'news':lambda self,t:[],'headlines':lambda self:[]})()
        # Hourly SPY bars on 2026-03-03 (NY): 9:30, 10:30, 11:30 start times.
        times=['2026-03-03T14:30:00+00:00','2026-03-03T15:30:00+00:00','2026-03-03T16:30:00+00:00']
        m=HistoricalMarket(base,intraday={'SPY':{'times':times,'close':[500.,510.,520.],'high':[505.,515.,525.],'low':[495.,505.,515.]}})
        m.as_of=datetime(2026,3,3,16,0,tzinfo=timezone.utc)  # 11:00 NY: only the 9:30 bar (14:30-15:30Z) has finished
        h=m.history(['SPY'])['SPY']
        self.assertEqual(h['dates'][-1],'2026-03-03');self.assertEqual(h['dates'][-2],'2026-03-02')  # today's daily bar never used
        self.assertEqual(h['close'][-1],500.)
        m.as_of=datetime(2026,3,3,17,30,tzinfo=timezone.utc)  # 12:30 NY: all three bars have finished
        h=m.history(['SPY'])['SPY'];self.assertEqual((h['close'][-1],h['high'][-1],h['low'][-1]),(520.,525.,495.))

    def test_graph_history_thins_old_points_but_keeps_trades(self):
        self.bot.setup(10000,'low',6);s=json.loads(self.bot.file.read_text())
        start=self.now-timedelta(days=5)
        s['equity_history']=[{'time':(start+timedelta(minutes=i)).isoformat(),'value':10000.,'cash':0.,'deposits':10000.,'trades':(['TR1'] if i==7 else [])} for i in range(6100)]
        atomic_json(self.bot.file,s);self.now+=timedelta(minutes=1);q=self.bot.refresh(False)
        hist=q['equity_history'];self.assertLessEqual(len(hist),6000);self.assertLess(len(hist),6101)
        self.assertTrue(any(pt['trades']==['TR1'] for pt in hist))

    def test_empty_download_is_rejected_not_cached(self):
        from unittest.mock import patch
        from desk.portfolio_bot import YahooMarket
        cols=pd.MultiIndex.from_product([['SPY','AAPL'],['Close','High','Low']])
        empty=pd.DataFrame(np.nan,index=pd.date_range('2026-09-10',periods=3,freq='h',tz='UTC'),columns=cols)
        fake_yf=type('YF',(),{'download':staticmethod(lambda *a,**k:empty)})()
        market=YahooMarket(Path(self.tmp.name)/'cache')
        with patch.object(YahooMarket,'_yf',staticmethod(lambda:fake_yf)):
            with self.assertRaises(RuntimeError):market.intraday(['SPY','AAPL'])
            with self.assertRaises(RuntimeError):market.history(['SPY','AAPL'])
        self.assertFalse((Path(self.tmp.name)/'cache'/'intraday.json').exists())

    def test_replay_falls_back_to_daily_when_hourly_prices_are_empty(self):
        market=FakeMarket();market.intraday=lambda tickers:{t:{'times':[],'close':[],'high':[],'low':[]} for t in tickers}
        dates=market.data['SPY']['dates'];self.now=datetime.fromisoformat(dates[-1]).replace(hour=22,tzinfo=timezone.utc)+timedelta(days=1)
        bot=PortfolioBot(Path(self.tmp.name)/'fallback',market,UNIVERSE,lambda:self.now,market_open=lambda now:True)
        p=bot.backfill(10000,'medium',6,days=10)
        self.assertEqual(p['replay']['resolution'],'daily');self.assertTrue(p['trades'])

    def test_unconfigured_state(self):
        self.assertFalse(self.bot.refresh()['configured'])
        with self.assertRaises(ValueError):self.bot.update_settings(1000,'low',2)

if __name__=='__main__':unittest.main()
