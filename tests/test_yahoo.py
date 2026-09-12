import unittest
import pandas as pd
from desk.yahoo import normalize
class YahooTests(unittest.TestCase):
 def test_actual_change_and_timestamp(self):
  h=pd.DataFrame({'Close':[100.,105.]},index=pd.date_range('2026-09-10',periods=2,tz='UTC'))
  q=normalize('SPY',h,{'regularMarketTime':pd.Timestamp('2026-09-11T20:00:00Z'),'currency':'USD'})
  self.assertAlmostEqual(q['change_pct'],5);self.assertIn('20:00:00',q['price_as_of'])
 def test_no_fake_zero_change(self):
  h=pd.DataFrame({'Close':[100.]},index=pd.date_range('2026-09-10',periods=1,tz='UTC'))
  self.assertIsNone(normalize('SPY',h,{})['change_pct'])
 def test_invalid_price(self):
  h=pd.DataFrame({'Close':[-1.]},index=pd.date_range('2026-09-10',periods=1,tz='UTC'))
  with self.assertRaises(ValueError):normalize('SPY',h,{})
