"""Forecast diagnostics on the reused validation sample, separate from trading profitability."""
from pathlib import Path
import json,numpy as np,pandas as pd
from .research import Candidate,load_bars,save_json
from .models import forecast
ROOT=Path(__file__).resolve().parents[1]
def main():
    df=load_bars(ROOT/'data/btcusdt_1h.csv',4);df=df.loc[df.index<pd.Timestamp('2026-04-01T00:00:00Z')]
    target=df.close.shift(-6)/df.close-1
    out=[]
    for folder,model in [('round-ml','ridge'),('round-tree','tree')]:
        c=Candidate(**json.loads((ROOT/'reports'/folder/'validation.json').read_text())['candidate'])
        pred,fits=forecast(df,alpha=c.fast,model=model)
        keep=(df.index>=pd.Timestamp('2025-01-01T00:00:00Z'))&pred.notna()&target.notna()
        y=target.loc[keep].to_numpy();p=pred.loc[keep].to_numpy()
        mse=float(np.mean((p-y)**2));zero=float(np.mean(y*y))
        diff=(p-y)**2-y*y
        # Non-overlapping 7-day blocks; descriptive interval for mean loss difference.
        n=(len(diff)//42)*42;blocks=diff[:n].reshape(-1,42).mean(axis=1)
        rng=np.random.default_rng(20260912)
        samples=blocks[rng.integers(0,len(blocks),size=(5000,len(blocks)))].mean(axis=1)
        out.append({'model':model,'candidate':c.key,'observations':len(y),'horizon_hours':24,
                    'rmse':float(np.sqrt(mse)),'zero_forecast_rmse':float(np.sqrt(zero)),
                    'mse_relative_to_zero':mse/zero,'directional_accuracy':float(np.mean(np.sign(y)==np.sign(p))),
                    'forecast_actual_correlation':float(np.corrcoef(y,p)[0,1]),
                    'fraction_above_entry_cost_buffer':float(np.mean(p>c.slow/10000)),
                    'mean_error_difference_95pct_block_interval':list(map(float,np.percentile(samples,[2.5,97.5]))),
                    'positive_difference_means_worse_than_zero':True,'bootstrap_repetitions':5000,
                    'limitations':'Overlapping 24-hour labels, small sample and model selection affect inference. Descriptive audit only, not proof of tradability or significance.'})
    save_json(ROOT/'reports/forecast-audit.json',out);print(json.dumps(out,indent=2))
if __name__=='__main__':main()
