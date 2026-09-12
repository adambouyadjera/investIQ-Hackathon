"""Free local ridge forecasting with purged, monthly rolling fits."""
from __future__ import annotations
import numpy as np
import pandas as pd

def _features_segment(df):
    c=df.close;r=c.pct_change();ema=c.ewm(span=50,adjust=False,min_periods=50).mean()
    slow=c.ewm(span=200,adjust=False,min_periods=200).mean()
    f=pd.DataFrame({
        'return_1':c.pct_change(1),'return_6':c.pct_change(6),'return_24':c.pct_change(24),
        'return_72':c.pct_change(72),'volatility_24':r.rolling(24).std(),
        'volatility_72':r.rolling(72).std(),'ema50_distance':c/ema-1,
        'ema200_distance':c/slow-1,'range':(df.high-df.low)/c,
        'volume_ratio':df.volume/df.volume.rolling(24).mean()-1,
    },index=df.index)
    return f.replace([np.inf,-np.inf],np.nan)

def features(df):
    groups=df['gap'].cumsum() if 'gap' in df else pd.Series(0,index=df.index)
    return pd.concat([_features_segment(part) for _,part in df.groupby(groups,sort=False)])

def forecast(df,alpha=10.,horizon=6,model="ridge"):
    """At each monthly boundary fit trailing 365 days; all labels end before boundary."""
    x=features(df);target=df.close.shift(-horizon)/df.close-1
    groups=df['gap'].cumsum() if 'gap' in df else pd.Series(0,index=df.index)
    target=target.where(groups==groups.shift(-horizon))
    pred=pd.Series(np.nan,index=df.index);fits=[]
    months=df.index.tz_localize(None).to_period('M')
    for month in months.unique():
        idx=np.flatnonzero(months==month);first=idx[0]
        # Conservative purge: training label's end must be strictly before this month's first bar.
        end=first-horizon
        begin=max(0,end-365*6)
        if end-begin<600:continue
        train=x.iloc[begin:end];y=target.iloc[begin:end]
        ok=train.notna().all(axis=1)&y.notna()
        if ok.sum()<500:continue
        a=train.loc[ok].to_numpy();b=y.loc[ok].to_numpy()
        mean=a.mean(axis=0);std=a.std(axis=0);std=np.where(std>1e-10,std,1.)
        z=np.clip((a-mean)/std,-8,8);design=np.column_stack([np.ones(len(z)),z])
        penalty=np.eye(design.shape[1])*alpha;penalty[0,0]=0
        coef=np.linalg.solve(design.T@design+penalty,design.T@b)
        test=x.iloc[idx];valid=test.notna().all(axis=1)
        ztest=np.clip((test.loc[valid].to_numpy()-mean)/std,-8,8)
        if model=='tree':
            from sklearn.ensemble import HistGradientBoostingRegressor
            estimator=HistGradientBoostingRegressor(max_iter=100,learning_rate=.05,max_leaf_nodes=7,max_depth=3,min_samples_leaf=50,l2_regularization=alpha,early_stopping=False,random_state=20260912)
            estimator.fit(z,b)
            pred.loc[test.index[valid]]=estimator.predict(ztest)
        else:
            pred.loc[test.index[valid]]=np.column_stack([np.ones(len(ztest)),ztest])@coef
        fits.append({'prediction_month':str(month),'train_start':train.index[0].isoformat(),
                     'last_feature_time':train.index[-1].isoformat(),
                     'last_label_time':df.index[end-1+horizon].isoformat(),
                     'prediction_start':df.index[first].isoformat(),'training_samples':int(ok.sum())})
    return pred,fits

def ridge_signals(df,c):
    pred,fits=forecast(df,alpha=float(c.fast),horizon=6,model="tree" if c.family=="tree" else "ridge")
    cprice=df.close
    tr=pd.concat([df.high-df.low,(df.high-cprice.shift()).abs(),(df.low-cprice.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    threshold=c.slow/10000
    # Only crossing the cost buffer creates a new entry; flat/no prediction is never a buy.
    enter=(pred>threshold)&(pred.shift()<=threshold)
    leave=pred<0
    return pd.DataFrame({'entry':enter.fillna(False),'leave':leave.fillna(False),'atr':atr},index=df.index),fits
