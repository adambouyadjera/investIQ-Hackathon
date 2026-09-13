import json,unittest
from datetime import datetime,timezone
from desk.portfolio_bot import RISK
from desk.simulator import build_plan,round_to_total,replay_plan,leaderboard
from tests.test_portfolio_bot import series

UNIVERSE={'SPY':('S&P 500 fund','etf','the 500 largest US companies',r'S&P'),'VTI':('Total market fund','etf','the whole US market',r'stock market'),
          'BND':('Bond fund','bond','US bonds',r'bond'),'GLD':('Gold fund','commodity','gold',r'gold'),'XLE':('Energy fund','etf','energy companies',r'oil'),
          'AAPL':('Apple','stock','phones',r'Apple'),'MSFT':('Microsoft','stock','software',r'Microsoft'),'NVDA':('NVIDIA','stock','chips',r'Nvidia'),
          'KO':('Coca-Cola','stock','drinks',r'Coca')}

class Market:
    def __init__(self):
        drift={'SPY':.2,'VTI':.18,'BND':.05,'GLD':.12,'XLE':.25,'AAPL':.4,'MSFT':.35,'NVDA':.6,'KO':.15}
        vol={'SPY':.12,'VTI':.13,'BND':.04,'GLD':.14,'XLE':.2,'AAPL':.25,'MSFT':.22,'NVDA':.45,'KO':.14}
        self.data={t:series(drift[t],vol[t],i+40) for i,t in enumerate(UNIVERSE)}
    def history(self,tickers):return {t:self.data[t] for t in tickers if t in self.data}
    def fundamentals(self,tickers):return {'AAPL':{'profitMargins':.26,'revenueGrowth':.08,'trailingPE':30.}}
    def news(self,t):return [{'title':'Apple profits rise','url':'https://example.com/apple','source':'Example News','published_at':'2026-09-10T12:00:00Z'}] if t=='AAPL' else []
    def headlines(self):return []

NOW=datetime(2026,9,12,15,tzinfo=timezone.utc)
plan=lambda *a:build_plan(*a,market=Market(),universe=UNIVERSE,now=NOW)

class SimulatorTests(unittest.TestCase):
    def test_percentages_and_dollars_add_up_exactly(self):
        p=plan(1000,150,'medium',12)
        self.assertAlmostEqual(sum(a['percent'] for a in p['assets']),100.0,places=6)
        self.assertAlmostEqual(sum(a['initial_amount'] for a in p['assets']),1000.0,places=6)
        self.assertAlmostEqual(sum(a['monthly_amount'] for a in p['assets']),150.0,places=6)
        self.assertEqual((p['totals']['percent'],p['totals']['initial'],p['totals']['monthly']),(100.0,1000.0,150.0))
        for a in p['assets']:self.assertLessEqual(abs(a['initial_amount']-a['percent']*10),0.06)  # 40% of $1,000 -> $400

    def test_rounding_keeps_the_total(self):
        self.assertEqual(sum(round_to_total([100/3]*3,100,0.1)),100.0)
        self.assertEqual(round_to_total([40,35,25],1000*0+100,0.1),[40.0,35.0,25.0])
        self.assertAlmostEqual(sum(round_to_total([333.3333]*3,1000,0.01)),1000.0)

    def test_low_risk_leans_on_funds_and_high_risk_allows_more_stocks(self):
        low,high=plan(5000,0,'low',24),plan(5000,0,'high',24)
        stock_pct=lambda p:sum(a['percent'] for a in p['assets'] if a['kind']=='stock')
        self.assertLessEqual(stock_pct(low),RISK['low']['stock_share']*100+1)
        funds_pct=sum(a['percent'] for a in low['assets'] if a['ticker'] in ('SPY','VTI','BND'))  # the test's broad, diversified funds
        self.assertGreaterEqual(funds_pct,60-0.5)
        broad={'SPY','VTI','BND'}
        self.assertTrue(all(a['percent']<=(35 if a['ticker'] in broad else RISK['low']['max_weight']*100)+0.5 for a in low['assets']))
        self.assertGreaterEqual(stock_pct(high),stock_pct(low))
        self.assertTrue(all(a['kind']!='crypto' for a in low['assets']+high['assets']))

    def test_projection_and_summary(self):
        p=plan(2000,100,'medium',24);pts=p['projection']['points'];s=p['summary']
        self.assertEqual(len(pts),25);self.assertEqual(pts[-1]['contributed'],2000+100*24)
        self.assertLessEqual(pts[-1]['pessimistic'],pts[-1]['expected']);self.assertLessEqual(pts[-1]['expected'],pts[-1]['optimistic'])
        self.assertEqual(s['total_contributed'],4400);self.assertAlmostEqual(s['expected_gain'],s['expected_end']-4400,places=2)
        self.assertLess(s['without_monthly_end'],s['expected_end']);self.assertGreater(s['monthly_effect'],0)
        r=p['replay'];self.assertIsNotNone(r)
        self.assertEqual(r['total_contributed'],2000+100*r['months_replayed'])
        self.assertAlmostEqual(sum(h['invested'] for h in r['holdings']),r['total_contributed'],places=1)
        self.assertEqual(len(r['months']),r['months_replayed']+1)

    def test_each_asset_is_explained_without_promises(self):
        p=plan(1000,50,'high',6)
        for a in p['assets']:
            for key in ('why','downside','role','risk_level'):self.assertTrue(a[key],key)
            for key in ('market','price_movement','indicators','fundamentals','volatility','news','risk_factors','why_amount'):self.assertIn(key,a['analysis'])
            self.assertIn(f"{a['percent']:.1f}%",a['analysis']['why_amount'])
        text=json.dumps(p).lower()
        for phrase in ('certain to','risk-free','will make','guaranteed profit'):self.assertNotIn(phrase,text)
        apple=[a for a in p['assets'] if a['ticker']=='AAPL']
        if apple:self.assertEqual(apple[0]['analysis']['news'][0]['source'],'Example News')

    def test_monthly_only_plan_splits_the_monthly_amount(self):
        p=plan(0,200,'medium',12)
        self.assertEqual(p['totals']['initial'],0.0);self.assertEqual(p['totals']['monthly'],200.0)
        self.assertIsNone(p['replay']['initial_only_value']);self.assertEqual(p['replay']['months'][0]['added'],0.0)

    def test_replay_math_on_known_prices(self):
        dates=[d.strftime('%Y-%m-%d') for d in __import__('pandas').bdate_range('2025-01-01',periods=300)]
        flat={'dates':dates,'close':[50.]*300,'high':[50.]*300,'low':[50.]*300}
        r=replay_plan({'SPY':flat,'BND':flat},{'SPY':.6,'BND':.4},1000,100,6)
        self.assertEqual((r['months_replayed'],r['capped']),(6,False))
        self.assertAlmostEqual(r['final_value'],1600.0);self.assertAlmostEqual(r['gain'],0.0)  # flat prices: value = money put in
        self.assertAlmostEqual(sum(h['shares'] for h in r['holdings'] if h['ticker']=='SPY'),1600*.6/50)
        rising={'dates':dates,'close':[50.]*299+[100.],'high':[50.]*299+[100.],'low':[50.]*299+[100.]}
        r=replay_plan({'SPY':rising},{'SPY':1.},1000,0,3)
        self.assertAlmostEqual(r['final_value'],2000.0);self.assertAlmostEqual(r['initial_only_value'],2000.0)
        long=replay_plan({'SPY':flat},{'SPY':1.},500,50,120)
        self.assertTrue(long['capped']);self.assertLess(long['months_replayed'],120)
        self.assertEqual(long['total_contributed'],500+50*long['months_replayed'])

    def test_leaderboard_ranks_everything_with_changes_since_previous_close(self):
        b=leaderboard('medium',12,market=Market(),universe=UNIVERSE,now=NOW)
        ranks=[r['rank'] for r in b['rows']]
        self.assertEqual(ranks,sorted(ranks));self.assertEqual(len(b['rows']),len(UNIVERSE))
        self.assertEqual(b['compared_to'],Market().data['SPY']['dates'][-2])
        self.assertTrue(all(r['rank_change'] is not None and r['score_change'] is not None for r in b['rows']))
        self.assertTrue({r['trend'] for r in b['rows']}<={'Uptrend','Mixed','Downtrend'})
        self.assertTrue(all((r['reason'] is None)==r['qualifies'] for r in b['rows']))
        self.assertIn('not a prediction',b['note'])

    def test_user_added_investment_is_always_in_the_plan(self):
        base=plan(1000,0,'medium',12);inside={a['ticker'] for a in base['assets']}
        extra=next((t for t in UNIVERSE if t not in inside),None)
        if extra is None:self.skipTest('every fixture investment already in the plan')
        p=build_plan(1000,0,'medium',12,market=Market(),universe=UNIVERSE,now=NOW,include=[extra.lower()])
        added=[a for a in p['assets'] if a['ticker']==extra]
        self.assertTrue(added);self.assertTrue(added[0]['added_by_user']);self.assertTrue(added[0]['why'].startswith('You added'))
        self.assertEqual((p['totals']['percent'],p['totals']['initial']),(100.0,1000.0));self.assertEqual(p['inputs']['include'],[extra])
        with self.assertRaises(ValueError):build_plan(1000,0,'medium',12,market=Market(),universe=UNIVERSE,now=NOW,include=['ZZZZ'])
        with self.assertRaises(ValueError):build_plan(1000,0,'medium',12,market=Market(),universe=UNIVERSE,now=NOW,include=list(UNIVERSE)[:6])

    def test_recent_news_counts_more_and_moves_rankings(self):
        from desk.portfolio_bot import news_signal
        items=[{'title':'Apple profits rise','published_at':'2026-09-12T12:00:00Z'},{'title':'Apple profits rise!','published_at':'2026-09-12T11:00:00Z'},
               {'title':'Apple shares plunge','published_at':'2026-09-02T12:00:00Z'}]
        got,tone,summary=news_signal(items,NOW)
        self.assertEqual(len(got),2);self.assertGreater(tone,0);self.assertEqual((summary['recent'],summary['positive'],summary['negative']),(1,1,1))
        class BadNews(Market):
            def news(self,t):return [{'title':'Nvidia shares plunge on lawsuit','url':'https://example.com/n','source':'X','published_at':'2026-09-12T13:00:00Z'}] if t=='NVDA' else []
        score=lambda b:next(r for r in b['rows'] if r['ticker']=='NVDA')
        good,bad=score(leaderboard('high',3,market=Market(),universe=UNIVERSE,now=NOW)),score(leaderboard('high',3,market=BadNews(),universe=UNIVERSE,now=NOW))
        self.assertLess(bad['score'],good['score']-0.05);self.assertEqual(bad['news']['negative'],1)
        self.assertEqual(bad['headlines'][0]['tone'],'negative')

    def test_live_board_reports_new_headlines_and_rank_moves(self):
        import desk.simulator as sim
        sim._live.clear()
        class Live(Market):
            items={}
            def news(self,t):return self.items.get(t,[])
        m=Live()
        first=sim.watch('high',3,market=m,universe=UNIVERSE,now=NOW)
        self.assertEqual((first['events'],first['version'],first['live']),([],1,True))
        m.items={'NVDA':[{'title':'Nvidia shares plunge on lawsuit','url':'https://example.com/n1','source':'X','published_at':'2026-09-12T14:30:00Z'}]}
        self.assertEqual(sim.live_tick(market=m,now=NOW),1)
        after=sim.watch('high',3,market=m,universe=UNIVERSE,now=NOW)
        self.assertEqual(after['version'],2)
        nv=[e for e in after['events'] if e['ticker']=='NVDA']
        self.assertTrue(nv);self.assertEqual(nv[0]['headline']['tone'],'negative')
        sim._live.clear();self.assertEqual(sim.live_tick(market=m,now=NOW),0)

    def test_news_archive_keeps_older_headlines_and_longer_plans_remember_more(self):
        import tempfile,os
        from desk.simulator import NewsArchive,latest_news
        from desk.portfolio_bot import news_signal,NEWS_MEMORY
        class Feed(Market):
            items={'AAPL':[{'title':'Apple profits rise','url':'https://e.com/1','source':'X','published_at':'2026-09-01T12:00:00Z'}]}
            def news(self,t):return self.items.get(t,[])
        with tempfile.TemporaryDirectory() as d:
            arc=NewsArchive(os.path.join(d,'a.json'));m=Feed()
            latest_news(m,['AAPL'],arc,NOW)
            m.items={'AAPL':[{'title':'Apple shares slump','url':'https://e.com/2','source':'X','published_at':'2026-09-12T12:00:00Z'}]}
            self.assertEqual([i['url'] for i in latest_news(m,['AAPL'],arc,NOW)['AAPL']],['https://e.com/2','https://e.com/1'])
        old_good=[{'title':f'Apple profits rise {n}','published_at':f'2026-09-0{n}T12:00:00Z'} for n in range(1,6)]
        new_bad=[{'title':'Apple shares slump','published_at':'2026-09-12T12:00:00Z'}]
        self.assertLess(news_signal(old_good+new_bad,NOW,**NEWS_MEMORY['short'])[1],0)
        self.assertGreater(news_signal(old_good+new_bad,NOW,**NEWS_MEMORY['long'])[1],0)

    def test_buy_signals_match_the_plan(self):
        b=leaderboard('medium',12,market=Market(),universe=UNIVERSE,now=NOW);p=plan(1000,0,'medium',12)
        self.assertEqual({x['ticker']:x['percent'] for x in b['buy_now']},{a['ticker']:a['percent'] for a in p['assets']})
        self.assertAlmostEqual(sum(x['percent'] for x in b['buy_now']),100.0)
        buys={x['ticker'] for x in b['buy_now']}
        for r in b['rows']:
            self.assertEqual(r['signal']=='Buy',r['ticker'] in buys)
            if r['signal']=='Avoid':self.assertFalse(r['qualifies'])

    def test_rejects_bad_inputs(self):
        for args in ((0,0,'low',12),(100,0,'low',0),(100,0,'extreme',12),(-5,10,'low',12),(100,0,'low',2.5)):
            with self.assertRaises(ValueError):plan(*args)

if __name__=='__main__':unittest.main()
