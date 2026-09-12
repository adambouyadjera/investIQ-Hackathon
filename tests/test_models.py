import unittest
import numpy as np,pandas as pd
from desk.models import features,forecast
class ModelTests(unittest.TestCase):
    def data(self):
        rng=np.random.default_rng(44);n=1500;c=100*np.exp(np.cumsum(rng.normal(0,.005,n)))
        return pd.DataFrame({'open':c,'high':c*1.01,'low':c*.99,'close':c,'volume':rng.uniform(10,20,n),'gap':False},index=pd.date_range('2023-01-01',periods=n,freq='4h',tz='UTC'))
    def test_label_purge(self):
        _,fits=forecast(self.data())
        self.assertTrue(fits)
        for f in fits:self.assertLess(pd.Timestamp(f['last_label_time']),pd.Timestamp(f['prediction_start']))
    def test_future_data_does_not_alter_prior_forecasts(self):
        d=self.data();a,_=forecast(d)
        changed=d.copy();changed.iloc[1200:,changed.columns.get_loc('close')]*=1.5
        b,_=forecast(changed)
        pd.testing.assert_series_equal(a.iloc[:1200],b.iloc[:1200])
    def test_features_reset_after_gap(self):
        d=self.data();d.iloc[800,d.columns.get_loc('gap')]=True
        f=features(d);self.assertTrue(f.iloc[800:999].ema200_distance.isna().all())
if __name__=='__main__':unittest.main()
