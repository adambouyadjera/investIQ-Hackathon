import asyncio
import unittest
from unittest.mock import patch
from desk.yahoo_stream import YahooStream, normalize_tick
class YahooStreamTests(unittest.TestCase):
 def test_normalize_tick(self):
  t=normalize_tick({'id':'SPY','price':764.29,'time':'1789247379000','change_percent':0.85,'currency':'USD'})
  self.assertEqual(t['symbol'],'SPY');self.assertAlmostEqual(t['price'],764.29);self.assertAlmostEqual(t['change_pct'],0.85);self.assertIn('2026-09-12',t['price_as_of'])
 def test_rejects_unknown_and_invalid(self):
  self.assertIsNone(normalize_tick({'id':'TSLA','price':1}))
  self.assertIsNone(normalize_tick({'id':'SPY','price':0}))
  self.assertIsNone(normalize_tick({'id':'SPY'}))
  self.assertIsNone(normalize_tick({'id':'SPY','price':1,'change_percent':float('nan')})['change_pct'])
 def test_fanout_and_shutdown(self):
  async def scenario():
   s=YahooStream()
   with patch.object(YahooStream,'_run',lambda self:asyncio.sleep(3600)):
    a,b=s.subscribe(),s.subscribe();task=s.task
    s.publish({'symbol':'SPY','price':1.0})
    self.assertEqual((await a.get())['price'],1.0);self.assertEqual((await b.get())['price'],1.0)
    s.unsubscribe(a);self.assertIs(s.task,task)
    s.unsubscribe(b);self.assertIsNone(s.task);await asyncio.sleep(0);self.assertTrue(task.cancelled())
    self.assertEqual(s.latest['SPY']['price'],1.0)
  asyncio.run(scenario())
 def test_slow_listener_drops_oldest(self):
  async def scenario():
   s=YahooStream()
   with patch.object(YahooStream,'_run',lambda self:asyncio.sleep(3600)):
    q=s.subscribe()
    for i in range(105):s.publish({'symbol':'SPY','price':float(i+1)})
    self.assertEqual(q.qsize(),100);self.assertEqual((await q.get())['price'],6.0)
    s.unsubscribe(q)
  asyncio.run(scenario())
