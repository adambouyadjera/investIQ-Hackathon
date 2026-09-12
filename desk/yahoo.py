"""Yahoo Finance reference quotes, independent of BTCUSDT paper execution."""
import json, math, time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from .paper import ROOT, locked, atomic_json
WATCHLIST={'BTC-USD':'Bitcoin / USD','ETH-USD':'Ethereum / USD','SPY':'S&P 500 ETF','QQQ':'Nasdaq-100 ETF','GLD':'Gold ETF'}
CACHE=ROOT/'state/yahoo-quotes.json'

def normalize(symbol, history, metadata):
    closes=history['Close'].dropna()
    if closes.empty:raise ValueError('No prices')
    price=float(closes.iloc[-1])
    if not math.isfinite(price) or price<=0:raise ValueError('Invalid price')
    previous=float(closes.iloc[-2]) if len(closes)>1 else None
    stamp=metadata.get('regularMarketTime')
    if hasattr(stamp,'timestamp'):stamp=stamp.timestamp()
    stamp=datetime.fromtimestamp(float(stamp),timezone.utc).isoformat() if stamp else None
    return {'symbol':symbol,'name':WATCHLIST[symbol],'price':price,'currency':metadata.get('currency','USD'),
            'change_pct':(price/previous-1)*100 if previous and math.isfinite(previous) and previous>0 else None,
            'price_as_of':stamp,'bar_date':str(history.index[-1].date()),'source':'Yahoo Finance','stale':False,
            'url':f'https://finance.yahoo.com/quote/{symbol}/','status':'ok'}

def fetch(symbol):
    import yfinance as yf
    try:
        t=yf.Ticker(symbol);h=t.history(period='5d',interval='1d',auto_adjust=False,actions=False,timeout=10)
        return normalize(symbol,h,t.get_history_metadata())
    except Exception:
        return {'symbol':symbol,'name':WATCHLIST[symbol],'status':'unavailable','source':'Yahoo Finance'}

def get_quotes():
    with locked(ROOT/'state/yahoo.lock'):
        try:old=json.loads(CACHE.read_text())
        except (OSError,ValueError):old={}
        if time.time()-old.get('checked_epoch',0)<300:return old
        import yfinance as yf
        folder=ROOT/'state/yfinance-cache';folder.mkdir(parents=True,exist_ok=True)
        yf.set_tz_cache_location(str(folder))
        with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,WATCHLIST))
        for i,row in enumerate(rows):
            if row['status']!='ok':
                cached=next((x for x in old.get('quotes',[]) if x['symbol']==row['symbol'] and x.get('price')),None)
                if cached:rows[i]={**cached,'stale':True,'status':'unavailable'}
        result={'source':'Yahoo Finance via yfinance','checked_epoch':time.time(),'checked_at':datetime.now(timezone.utc).isoformat(),'quotes':rows,
                'note':'Reference quotes may be delayed or from the last trading session. Change compares the latest daily close/observation with the prior daily close. BTC-USD is not BTC/USDT.'}
        atomic_json(CACHE,result);return result
if __name__=='__main__':print(json.dumps(get_quotes(),indent=2))
