"""Exploratory CSCV selection diagnostic on development quarters, never the final holdout."""
from pathlib import Path
import itertools,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def main():
    all_rows=[]
    for name in ['', 'round-two','round-ml','round-tree']:
        p=ROOT/'reports'/name/'development-leaderboard.json'
        if p.exists():all_rows.extend(json.loads(p.read_text()))
    # All samples are independently started training quarters, not hypothetical future observations.
    matrix=np.array([[q['net_return'] for q in row['quarterly']] for row in all_rows]).T
    total,n=matrix.shape;indices=set(range(total));ranks=[];records=[]
    for selected in itertools.combinations(range(total),total//2):
        other=sorted(indices-set(selected));a=matrix[list(selected)].mean(axis=0);b=matrix[other].mean(axis=0)
        winner=int(np.argmax(a))
        rank=(np.count_nonzero(b<b[winner])+.5*np.count_nonzero(b==b[winner]))/n
        ranks.append(rank)
        records.append({'in_sample_mean':float(a[winner]),'other_half_mean':float(b[winner]),'relative_rank':float(rank)})
    report={'method':'CSCV-style diagnostic on 12 development calendar-quarter returns with mean-return selection',
            'not_a_forecast':True,'not_the_original_selection_score':True,'trials':n,'partitions':len(ranks),
            'fraction_winner_below_other_half_median':float(np.mean(np.array(ranks)<.5)),
            'median_other_half_rank':float(np.median(ranks)),
            'average_in_sample_quarter_return':float(np.mean([r['in_sample_mean'] for r in records])),
            'average_other_half_quarter_return':float(np.mean([r['other_half_mean'] for r in records])),
            'limitations':'Only 12 quarters; chronological dependence, flat quarter starts, reused public history and different scoring limit inference. This does not establish future profitability or a calibrated probability for the deployed process.',
            'holdout_accessed':False}
    (ROOT/'reports/selection-audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
