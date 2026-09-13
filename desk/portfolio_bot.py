"""Simulated stock & ETF portfolio bot — paper trading with virtual money only.

Rule-based analysis of free Yahoo Finance data (prices, fundamentals, headlines) plus the desk's publisher RSS feed.
It never places real orders and never promises returns; every trade stores a plain-language explanation built from
the numbers the bot actually used.
"""
from __future__ import annotations
import bisect, json, math, re, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from .paper import ROOT, locked, atomic_json

SLIPPAGE = 0.0005   # simulated price difference per trade; no commission
MIN_TRADE = 1.0
MIN_SCORE = 0.45
REVIEW_MINUTES = 5  # the bot re-analyzes around the clock; stocks/ETFs only fill while the US market is open
TRIM_BAND = 0.0075  # rebalance a holding once it drifts this share of the portfolio away from its target (0.75%: most active and, in the past-month hourly replay, the best result)
HOLD_BONUS = 0.03   # score bonus for current holdings, so near-ties don't cause in-and-out trading
HOLD_SLACK = 0.05   # holdings may stay until their score falls this far below the minimum
DISCLAIMER = ('Simulated paper trade with virtual money. This is an automated, rule-based decision, not financial advice. '
              'No result is guaranteed — prices can move against any investment.')
METHOD = ('Rule-based scoring, not a prediction: the bot compares recent price momentum, moving-average trends, RSI, '
          'volatility, company fundamentals and the tone of recent headlines across every stock, ETF and cryptocurrency it follows.')

# ticker: (name, kind, what it holds, headline keywords)
UNIVERSE = {
    'SPY': ('SPDR S&P 500 ETF', 'etf', 'the 500 largest US companies', r'S&P 500|Wall Street|US stocks'),
    'QQQ': ('Invesco QQQ Trust', 'etf', 'the 100 largest Nasdaq companies, mostly technology', r'Nasdaq|tech stocks'),
    'VTI': ('Vanguard Total Stock Market ETF', 'etf', 'the whole US stock market', r'US stocks|stock market'),
    'IWM': ('iShares Russell 2000 ETF', 'etf', 'about 2,000 small US companies', r'small[- ]cap|Russell 2000'),
    'VXUS': ('Vanguard Total International Stock ETF', 'etf', 'companies outside the US', r'global stocks|European stocks|Asian stocks'),
    'XLV': ('Health Care Select Sector SPDR', 'etf', 'large US health-care companies', r'health ?care|pharma|drugmakers?'),
    'XLF': ('Financial Select Sector SPDR', 'etf', 'large US banks and financial companies', r'\bbanks?\b|lenders?'),
    'XLE': ('Energy Select Sector SPDR', 'etf', 'large US oil and energy companies', r'\boil\b|energy|OPEC'),
    'TLT': ('iShares 20+ Year Treasury Bond ETF', 'bond', 'long-term US government bonds', r'Treasur(y|ies)|bond yields?|interest rates?'),
    'BND': ('Vanguard Total Bond Market ETF', 'bond', 'a broad mix of US bonds', r'\bbonds?\b|interest rates?'),
    'GLD': ('SPDR Gold Shares', 'commodity', 'gold', r'\bgold\b'),
    'AAPL': ('Apple', 'stock', 'iPhones, Macs and services', r'\bApple\b|iPhone'),
    'MSFT': ('Microsoft', 'stock', 'software and cloud computing', r'Microsoft'),
    'NVDA': ('NVIDIA', 'stock', 'computer chips for AI and gaming', r'Nvidia'),
    'AMZN': ('Amazon', 'stock', 'online shopping and cloud computing', r'Amazon'),
    'GOOGL': ('Alphabet (Google)', 'stock', 'Google search, YouTube and cloud', r'Alphabet|Google'),
    'JPM': ('JPMorgan Chase', 'stock', 'banking', r'JPMorgan'),
    'JNJ': ('Johnson & Johnson', 'stock', 'medicines and medical devices', r'Johnson & Johnson'),
    'KO': ('Coca-Cola', 'stock', 'soft drinks', r'Coca-Cola'),
    'PG': ('Procter & Gamble', 'stock', 'household products', r'Procter'),
    'BTC-USD': ('Bitcoin', 'crypto', 'the Bitcoin digital currency', r'bitcoin|\bBTC\b'),
    'ETH-USD': ('Ethereum', 'crypto', 'the Ethereum digital currency', r'ethereum|\bether\b'),
}
RISK = {
    'low':    {'label': 'Low', 'cash': 0.25, 'max_weight': 0.20, 'picks': 6, 'max_vol': 0.30, 'stock_share': 0.20, 'crypto_share': 0.0, 'sector_cap': 0.30, 'stop': 0.08, 'vol_penalty': 0.8},
    'medium': {'label': 'Medium', 'cash': 0.10, 'max_weight': 0.25, 'picks': 5, 'max_vol': 0.50, 'stock_share': 0.50, 'crypto_share': 0.10, 'sector_cap': 0.35, 'stop': 0.12, 'vol_penalty': 0.4},
    'high':   {'label': 'High', 'cash': 0.05, 'max_weight': 0.35, 'picks': 4, 'max_vol': 0.90, 'stock_share': 0.85, 'crypto_share': 0.20, 'sector_cap': 0.50, 'stop': 0.18, 'vol_penalty': 0.1},
}
SECTORS = {'SPY': 'broad US market', 'VTI': 'broad US market', 'IWM': 'broad US market', 'VXUS': 'international', 'TLT': 'bonds', 'BND': 'bonds',
           'QQQ': 'technology', 'AAPL': 'technology', 'MSFT': 'technology', 'NVDA': 'technology', 'GOOGL': 'technology', 'AMZN': 'technology',
           'XLF': 'financials', 'JPM': 'financials', 'XLE': 'energy', 'XLV': 'health care', 'JNJ': 'health care',
           'KO': 'consumer staples', 'PG': 'consumer staples', 'GLD': 'gold',
           'BTC-USD': 'crypto', 'ETH-USD': 'crypto'}
DIVERSIFIED = {'broad US market', 'international', 'bonds'}  # already spread across many industries; not sector-capped
TIMEFRAME = {
    'short':  {'label': 'Short-term', 'holding': 'a few days to a few weeks', 'rebalance_days': 1, 'review': 'day', 'trend': 'sma20',
               'focus': 'It favors investments with strong recent momentum whose RSI is not overheated.',
               'weights': {'m1': .35, 'm3': .15, 'm6': 0, 'm12': 0, 'trend': .2, 'rsi': .2, 'fund': 0, 'news': .1}},
    'medium': {'label': 'Medium-term', 'holding': 'a few weeks to a few months', 'rebalance_days': 7, 'review': 'week', 'trend': 'sma50',
               'focus': 'It favors steady uptrends over the last three to six months.',
               'weights': {'m1': .1, 'm3': .3, 'm6': .2, 'm12': 0, 'trend': .2, 'rsi': .05, 'fund': .1, 'news': .05}},
    'long':   {'label': 'Long-term', 'holding': 'several months or longer', 'rebalance_days': 30, 'review': 'month', 'trend': 'sma200',
               'focus': 'It favors solid company finances, long uptrends and lower volatility.',
               'weights': {'m1': 0, 'm3': .1, 'm6': .2, 'm12': .2, 'trend': .15, 'rsi': 0, 'fund': .3, 'news': .05}},
}
TREND_DAYS = {'sma20': 20, 'sma50': 50, 'sma200': 200}
COMPONENT_LABEL = {'m1': '1-month momentum', 'm3': '3-month momentum', 'm6': '6-month momentum', 'm12': '12-month momentum',
                   'trend': 'price trend', 'rsi': 'RSI balance', 'fund': 'fundamentals', 'news': 'headline tone'}
KIND_RISK = {'stock': 'A single company can fall sharply on bad earnings, lawsuits or new competition.',
             'etf': 'Even a diversified fund falls when its whole market or sector falls.',
             'bond': 'Bond funds lose value when interest rates rise.',
             'commodity': 'Gold pays no interest or dividends and can swing with currencies and market fear.',
             'crypto': 'Crypto can fall 20% or more within days, trades around the clock, and has no company profits behind its price.'}
POSITIVE = re.compile(r"\b(beats?|record|surges?|soars?|jumps?|gains?|rall(y|ies)|growth|upgrades?|strong|profits?|rises?|higher|boosts?|wins?)\b", re.I)
NEGATIVE = re.compile(r"\b(miss(es)?|plunges?|falls?|drops?|slumps?|cuts?|downgrades?|weak|loss(es)?|lawsuits?|probe|recalls?|declines?|lower|fears?|warnings?|layoffs?|crash(es)?)\b", re.I)


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None

def _usd(x): return f'${x:,.2f}'
def _pc(x): return 'not available' if x is None else f'{x:+.1%}'
def _iso(dt): return dt.astimezone(timezone.utc).isoformat()


class ConfirmationRequired(ValueError):
    """A change would reduce or reset an active simulated portfolio; the user must confirm it first."""


def timeframe_for(months):
    return 'short' if months <= 3 else ('medium' if months <= 12 else 'long')


def _validate(amount, risk, months):
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 100 <= amount <= 1_000_000:
        raise ValueError('Choose an amount between $100 and $1,000,000.')
    if risk not in RISK:
        raise ValueError('Choose Low, Medium or High risk.')
    if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 120:
        raise ValueError('Choose an investment period between 1 and 120 months.')


class YahooMarket:
    """Cached public Yahoo Finance data: prices every 5 minutes, fundamentals daily, headlines hourly."""
    def __init__(self, cache_dir=None):
        self.dir = Path(cache_dir or ROOT / 'state/portfolio-market')

    def _cached(self, name, ttl, fetch):
        path = self.dir / f'{name}.json'
        with locked(self.dir / f'{name}.lock'):
            try:
                old = json.loads(path.read_text())
            except (OSError, ValueError):
                old = None
            if old and time.time() - old['epoch'] < ttl:
                return old['data']
            try:
                data = fetch()
            except Exception:  # third-party client raises many types; serve stale data rather than nothing
                if old:
                    return old['data']
                raise RuntimeError(f'Market data unavailable ({name})')
            atomic_json(path, {'epoch': time.time(), 'data': data})
            return data

    @staticmethod
    def _yf():
        import yfinance as yf
        yf.set_tz_cache_location(str(ROOT / 'state/yfinance-cache'))
        return yf

    def history(self, tickers):
        def fetch():
            df = self._yf().download(list(tickers), period='10y', interval='1d', auto_adjust=True, progress=False, group_by='ticker', threads=True)
            out = {}
            for t in tickers:
                try:
                    sub = df[t].dropna(subset=['Close'])
                except KeyError:
                    continue
                if len(sub) >= 60:
                    out[t] = {'dates': [d.strftime('%Y-%m-%d') for d in sub.index],
                              **{k.lower(): [round(float(v), 4) for v in sub[k]] for k in ('Close', 'High', 'Low')}}
            # Rate limits and outages can return empty frames instead of errors; treat a thin result as a failure
            # so the cache keeps serving the last complete download.
            if 'SPY' not in out or len(out) < 0.8 * len(tickers):
                raise RuntimeError('incomplete prices')
            return out
        return self._cached('history', 120, fetch)  # daily bars' last row tracks the live price

    def intraday(self, tickers):
        def fetch():
            df = self._yf().download(list(tickers), period='60d', interval='1h', auto_adjust=True, progress=False, group_by='ticker', threads=True)
            out = {}
            for t in tickers:
                try:
                    sub = df[t].dropna(subset=['Close'])
                except KeyError:
                    continue
                if sub.empty:
                    continue
                idx = sub.index.tz_convert('UTC') if sub.index.tz is not None else sub.index.tz_localize('UTC')
                out[t] = {'times': [ts.isoformat() for ts in idx], **{k.lower(): [round(float(v), 4) for v in sub[k]] for k in ('Close', 'High', 'Low')}}
            if 'SPY' not in out or len(out) < 0.8 * len(tickers):
                raise RuntimeError('incomplete intraday prices')
            return out
        return self._cached('intraday', 600, fetch)

    def fundamentals(self, tickers):
        keys = ['trailingPE', 'forwardPE', 'profitMargins', 'revenueGrowth', 'earningsGrowth', 'dividendYield', 'beta', 'marketCap', 'netExpenseRatio']
        def one(t):
            try:
                info = self._yf().Ticker(t).info or {}
            except Exception:
                return t, {}
            return t, {k: _num(info.get(k)) for k in keys}
        def fetch():
            with ThreadPoolExecutor(max_workers=6) as pool:
                return dict(pool.map(one, tickers))
        try:
            return self._cached('fundamentals', 86400, fetch)
        except RuntimeError:
            return {}

    def news(self, ticker):
        def fetch():
            items = []
            for n in (self._yf().Ticker(ticker).news or [])[:10]:
                c = n.get('content', n)
                url = (c.get('canonicalUrl') or c.get('clickThroughUrl') or {}).get('url') or c.get('link')
                published = c.get('pubDate') or (datetime.fromtimestamp(c['providerPublishTime'], timezone.utc).isoformat() if c.get('providerPublishTime') else None)
                if c.get('title') and isinstance(url, str) and url.startswith('https://'):
                    items.append({'title': c['title'][:300], 'url': url, 'source': (c.get('provider') or {}).get('displayName') or c.get('publisher') or 'Yahoo Finance', 'published_at': published})
            return items
        try:
            return self._cached(f'news-{ticker}', getattr(self, 'news_ttl', 3600), fetch)
        except RuntimeError:
            return []

    def headlines(self):
        try:
            from .news import get_news
            return get_news().get('items', [])
        except Exception:
            return []


class HistoricalMarket:
    """Shows the bot only what was known at `as_of`, so a replay of past days can't peek at later prices or news.

    With hourly prices, each day is completed daily bars up to yesterday plus today's finished hourly bars."""
    def __init__(self, base, crypto=(), intraday=None):
        self.base, self.crypto, self.intraday = base, set(crypto), intraday
        self.as_of, self._full, self._bar_ends = None, None, {}

    def history(self, tickers):
        if self._full is None:
            self._full = self.base.history(tickers)
        out = {}
        for t, v in self._full.items():
            if self.intraday is None:
                day = self.as_of.astimezone(NY).date().isoformat()
                # A crypto daily bar only closes at midnight UTC, so use the day before; stock bars are final at 4pm ET.
                n = bisect.bisect_left(v['dates'], day) if t in self.crypto else bisect.bisect_right(v['dates'], day)
                if n >= 60:
                    out[t] = {k: v[k][:n] for k in ('dates', 'close', 'high', 'low')}
                continue
            today = self.as_of.astimezone(timezone.utc if t in self.crypto else NY).date()
            n = bisect.bisect_left(v['dates'], today.isoformat())
            if n < 60:
                continue
            series = {k: list(v[k][:n]) for k in ('dates', 'close', 'high', 'low')}
            bars = self._finished_bars_today(t, today)
            if bars:
                series['dates'].append(today.isoformat()); series['close'].append(bars[-1][0])
                series['high'].append(max(b[1] for b in bars)); series['low'].append(min(b[2] for b in bars))
            out[t] = series
        if not out:
            raise RuntimeError('No prices for this replay moment')
        return out

    def _finished_bars_today(self, t, today):
        h = self.intraday.get(t)
        if not h:
            return []
        if t not in self._bar_ends:
            self._bar_ends[t] = [datetime.fromisoformat(x) + timedelta(hours=1) for x in h['times']]
        ends = self._bar_ends[t]
        tz = timezone.utc if t in self.crypto else NY
        i, bars = bisect.bisect_right(ends, self.as_of) - 1, []
        while i >= 0 and (ends[i] - timedelta(hours=1)).astimezone(tz).date() == today:
            bars.append((h['close'][i], h['high'][i], h['low'][i])); i -= 1
        return bars[::-1]

    def fundamentals(self, tickers):
        return self.base.fundamentals(tickers)  # Yahoo has no point-in-time fundamentals; replay explanations say so

    def _known(self, items):
        known = []
        for i in items:
            try:
                if i.get('published_at') and datetime.fromisoformat(i['published_at'].replace('Z', '+00:00')) <= self.as_of:
                    known.append(i)
            except (TypeError, ValueError):
                continue
        return known

    def news(self, ticker):
        return self._known(self.base.news(ticker))

    def headlines(self):
        return self._known(self.base.headlines())


def metrics(series):
    close = pd.Series(series['close'], dtype=float)
    high = pd.Series(series['high'], dtype=float)
    low = pd.Series(series['low'], dtype=float)
    n = len(close); price = float(close.iloc[-1])
    ret = lambda d: _num(price / close.iloc[-1 - d] - 1) if n > d else None
    daily = close.pct_change().dropna()
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    down = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    sma = lambda w: _num(close.tail(w).mean()) if n >= w else None
    year = close.tail(252)
    return {'price': price, 'date': series['dates'][-1], 'w1': ret(5), 'm1': ret(21), 'm3': ret(63), 'm6': ret(126), 'm12': ret(252),
            'rsi': 100.0 if not down else _num(100 - 100 / (1 + up / down)),
            'sma20': sma(20), 'sma50': sma(50), 'sma200': sma(200),
            'vol20': _num(daily.tail(20).std() * math.sqrt(252)) if len(daily) >= 20 else None,
            'vol': _num(daily.tail(60).std() * math.sqrt(252)) if len(daily) >= 60 else None,
            'high52': _num(high.tail(252).max()), 'low52': _num(low.tail(252).min()),
            'max_drawdown': _num((year / year.cummax() - 1).min())}


# How far back news matters for each time period: short plans react to today's headlines, long plans remember weeks of them.
NEWS_MEMORY = {'short': {'half_life_hours': 24, 'limit': 10}, 'medium': {'half_life_hours': 72, 'limit': 25}, 'long': {'half_life_hours': 336, 'limit': 60}}


def news_signal(items, now, limit=8, half_life_hours=24):
    """Recency-weighted headline tone from -1 (bad) to 1 (good): a headline loses half its weight every `half_life_hours`.
    Few or old headlines are pulled toward neutral so a single story can't swing a ranking on its own."""
    seen, out = set(), []
    for i in items:
        key = re.sub(r'\W+', ' ', i.get('title', '')).strip().lower()
        if key and key not in seen:
            seen.add(key); out.append({**i, 'tone': headline_tone(i['title'])})
    for i in out:
        try:
            i['_age'] = max(0., (now - datetime.fromisoformat(i['published_at'].replace('Z', '+00:00'))).total_seconds() / 3600)
        except (TypeError, ValueError, AttributeError, KeyError):
            i['_age'] = None
    out = sorted(out, key=lambda i: i['_age'] if i['_age'] is not None else 1e9)[:limit]
    weights = [0.5 ** (i['_age'] / half_life_hours) if i['_age'] is not None else 0.1 for i in out]
    total = sum(weights)
    tone = sum(w * {'positive': 1, 'negative': -1}.get(i['tone'], 0) for w, i in zip(weights, out)) / total if total else 0.
    tone *= min(1., total / 2)
    summary = {k: sum(1 for i in out if i['tone'] == k) for k in ('positive', 'negative', 'neutral')}
    summary.update(total=len(out), oldest_at=next((i.get('published_at') for i in reversed(out) if i['_age'] is not None), None), recent=sum(1 for i in out if i['_age'] is not None and i['_age'] <= 24), latest_at=out[0].get('published_at') if out else None, tone=round(tone, 3))
    return [{k: v for k, v in i.items() if k != '_age'} for i in out], tone, summary


def headline_tone(title):
    p, n = len(POSITIVE.findall(title)), len(NEGATIVE.findall(title))
    return 'positive' if p > n else ('negative' if n > p else 'neutral')


def fundamentals_view(kind, f, holds):
    if kind == 'crypto':
        return 0.4, (f'This is {holds}, not a company: there are no profits, sales or dividends to analyze. '
                     'Its price depends only on supply and demand, which is why it can swing so much.')
    if kind != 'stock':
        er, pe = _num(f.get('netExpenseRatio')), _num(f.get('trailingPE'))
        text = f'This is a fund that holds many investments ({holds}), so there is no single company to judge.'
        if er is not None:
            text += f' Its yearly fee is {er:.2f}% of the money invested.'
        if pe is not None and kind == 'etf':
            text += f' The companies inside trade at about {pe:.0f}× their yearly profits on average.'
        return (0.6 if er is not None and er <= 0.2 else 0.5), text
    parts, bits = [], []
    pm, rg = _num(f.get('profitMargins')), _num(f.get('revenueGrowth'))
    pe = _num(f.get('trailingPE')) or _num(f.get('forwardPE'))
    if pm is not None:
        parts.append(min(1., max(0., pm / 0.3))); bits.append(f'keeps {pm:.0%} of its sales as profit')
    if rg is not None:
        parts.append(min(1., max(0., (rg + 0.05) / 0.3))); bits.append(f"had sales {'grow' if rg >= 0 else 'shrink'} {abs(rg):.0%} compared with a year earlier")
    if pe is not None and pe > 0:
        parts.append(1.0 if pe <= 20 else max(0., 1 - (pe - 20) / 40))
        bits.append(f"is priced at about ${pe:.0f} for each $1 of yearly profit ({'cheap' if pe < 15 else 'reasonable' if pe <= 25 else 'expensive'} compared with typical companies)")
    if not parts:
        return 0.5, 'Company financial data was not available, so fundamentals were treated as neutral.'
    return float(np.mean(parts)), 'The company ' + '; '.join(bits) + '.'


def market_regime(spy):
    if not spy or spy['sma200'] is None:
        return {'label': 'unknown', 'volatility': 'unknown', 'risk_off': False, 'text': 'Market-wide data for the S&P 500 was not available.'}
    above = spy['price'] > spy['sma200']; m1 = spy['m1'] or 0.; vol = spy['vol20'] or 0.
    risk_off = (not above) and m1 < -0.05
    mood = 'rising' if above and m1 > 0 else ('falling' if risk_off else 'mixed')
    calm = 'calm' if vol < 0.15 else ('normal' if vol < 0.25 else 'choppy')
    return {'label': mood, 'volatility': calm, 'risk_off': risk_off,
            'text': (f"The overall US market (S&P 500 fund SPY) was at {_usd(spy['price'])}, {'above' if above else 'below'} its 200-day average, "
                     f"and moved {m1:+.1%} over the past month. Day-to-day swings were {calm} ({vol:.0%} yearly volatility).")}


def allocate(picks, budget, r, risk):
    if not picks:
        return {}
    raw = {a['ticker']: (a['score'] if risk == 'high' else a['score'] / max(a['metrics']['vol'], 0.05)) for a in picks}
    w = {t: budget * v / sum(raw.values()) for t, v in raw.items()}
    stocks = [a['ticker'] for a in picks if a['kind'] == 'stock']
    crypto = [a['ticker'] for a in picks if a['kind'] == 'crypto']
    sectors = {}
    for a in picks:
        if SECTORS.get(a['ticker']) and SECTORS[a['ticker']] not in DIVERSIFIED:
            sectors.setdefault(SECTORS[a['ticker']], []).append(a['ticker'])
    for _ in range(10):  # caps only shrink weights; anything trimmed stays in cash (conservative)
        changed = False
        for t in w:
            if w[t] > r['max_weight'] + 1e-9:
                w[t] = r['max_weight']; changed = True
        share = sum(w[t] for t in stocks)
        if share > r['stock_share'] + 1e-9:
            for t in stocks:
                w[t] *= r['stock_share'] / share
            changed = True
        crypto_total = sum(w[t] for t in crypto)
        if crypto_total > r['crypto_share'] + 1e-9:
            for t in crypto:
                w[t] *= r['crypto_share'] / crypto_total
            changed = True
        for members in sectors.values():
            total = sum(w[t] for t in members)
            if total > r['sector_cap'] + 1e-9:
                for t in members:
                    w[t] *= r['sector_cap'] / total
                changed = True
        if not changed:
            break
    return {t: round(v, 4) for t, v in w.items() if v >= 0.01}


def analyze(history, fundamentals, news, headlines, risk, timeframe, universe=UNIVERSE, held=(), news_weight=None, now=None):
    r, tf = RISK[risk], TIMEFRAME[timeframe]; w = tf['weights']
    if news_weight is not None:  # Simulator recommendations: latest news gets a fixed, larger share of the score
        base = {k: v for k, v in w.items() if k != 'news'}; total = sum(base.values())
        w = {**{k: v * (1 - news_weight) / total for k, v in base.items()}, 'news': news_weight}
        now = now or datetime.now(timezone.utc)
    rows = {t: metrics(history[t]) for t in universe if t in history and len(history[t]['close']) >= 2}
    ranks = {k: pd.Series({t: m[k] for t, m in rows.items() if m[k] is not None}, dtype=float).rank(pct=True) for k in ('m1', 'm3', 'm6', 'm12')}
    regime = market_regime(rows.get('SPY'))
    assets = {}
    for t, m in rows.items():
        name, kind, holds, pattern = universe[t]
        rx = re.compile(pattern, re.I)
        if news_weight is None:
            items = news.get(t) or [h for h in headlines if rx.search(h.get('title', ''))]
            items = [{**i, 'tone': headline_tone(i['title'])} for i in items[:3]]
            tone = sum({'positive': 1, 'negative': -1}.get(i['tone'], 0) for i in items) / len(items) if items else 0.
            summary = None
        else:
            # A stock's own Yahoo news is tagged to it; keyword-matched site headlines are only a fallback because they can match the wrong story.
            items, tone, summary = news_signal(news.get(t) or [h for h in headlines if rx.search(h.get('title', ''))], now, **NEWS_MEMORY[timeframe])
        fscore, ftext = fundamentals_view(kind, fundamentals.get(t) or {}, holds)
        trend = 1.0 if m['sma50'] and m['sma200'] and m['price'] > m['sma50'] > m['sma200'] else (0.5 if m['sma200'] and m['price'] > m['sma200'] else 0.)
        comps = {k: float(ranks[k].get(t, .5)) for k in ranks}
        comps.update(trend=trend, rsi=max(0., 1 - abs((m['rsi'] if m['rsi'] is not None else 55) - 55) / 45), fund=fscore, news=(tone + 1) / 2)
        vol, line = m['vol'], m[tf['trend']]
        score = sum(w[k] * comps[k] for k in w) / sum(w.values()) - (r['vol_penalty'] * max(0., vol - 0.15) * 0.5 if vol is not None else 0.)
        blockers = []
        if kind == 'crypto' and not r['crypto_share']:
            blockers.append(f"crypto is not used at {r['label'].lower()} risk")
        if vol is None or line is None:
            blockers.append('there is not enough price history to judge it')
        if vol is not None and vol > r['max_vol']:
            blockers.append(f"it is too jumpy for {r['label'].lower()} risk ({vol:.0%} yearly volatility; the limit is {r['max_vol']:.0%})")
        if line is not None and m['price'] < line:
            blockers.append(f"its price is below its {TREND_DAYS[tf['trend']]}-day average, a sign of a downtrend")
        if score < (MIN_SCORE - HOLD_SLACK if t in held else MIN_SCORE):  # a little slack for holdings avoids in-and-out trading
            blockers.append(f'its overall score ({score:.2f}) is below the {MIN_SCORE:.2f} minimum')
        assets[t] = {'ticker': t, 'name': name, 'kind': kind, 'holds': holds, 'sector': SECTORS.get(t), 'metrics': m, 'fundamentals_text': ftext,
                     'news': items, 'components': comps, 'score': score, 'blockers': blockers,
                     'weights': w, 'news_summary': summary, 'news_weighted': news_weight}
    ranked = sorted(assets.values(), key=lambda a: -a['score'])
    for i, a in enumerate(ranked):
        a['rank'] = i + 1
    eligible = sorted((a for a in ranked if not a['blockers']), key=lambda a: -(a['score'] + (HOLD_BONUS if a['ticker'] in held else 0.)))
    # Crypto gets its own small slot (it can't compete with stocks for the main picks), so the plan still has
    # something that can trade nights and weekends. It must pass the same checks, and allocate() caps its share.
    picks = [a for a in eligible if a['kind'] != 'crypto'][:r['picks']]
    if r['crypto_share']:
        picks += [a for a in eligible if a['kind'] == 'crypto'][:1 if r['crypto_share'] <= 0.1 else 2]
    cash = min(0.9, r['cash'] + (0.15 if regime['risk_off'] and risk != 'high' else 0.))
    return {'assets': assets, 'ranked': [a['ticker'] for a in ranked], 'regime': regime, 'cash_reserve': cash,
            'targets': allocate(picks, 1 - cash, r, risk)}


NY = ZoneInfo('America/New_York')


def us_market_open(now):
    ny = now.astimezone(NY)
    return ny.weekday() < 5 and (9, 30) <= (ny.hour, ny.minute) < (16, 0)  # regular session; exchange holidays are not modelled


def next_market_open(now):
    ny = now.astimezone(NY)
    day = ny.replace(hour=9, minute=30, second=0, microsecond=0)
    if ny >= day:
        day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.astimezone(timezone.utc)


def price_note(now, last_date, kind=None):
    if kind == 'crypto':
        return 'Crypto trades 24 hours a day, 7 days a week. Prices come from Yahoo Finance and can be a few minutes delayed.'
    if us_market_open(now):
        return 'US markets were open. Prices come from Yahoo Finance and can be delayed by about 15 minutes.'
    return f'US markets were closed, so the bot used the latest available closing price (from {last_date}).'


def explain(action, reason, a, analysis, settings, portfolio_value, value, avg_cost, now):
    r, tf = RISK[settings['risk']], TIMEFRAME[settings['timeframe']]
    m, A, reg = a['metrics'], analysis['assets'], analysis['regime']
    target = analysis['targets'].get(a['ticker'], 0.)
    risk_word, plan = r['label'].lower(), tf['label'].lower()
    vol = m['vol'] or 0.; month_move = vol * math.sqrt(21 / 252); days = TREND_DAYS[tf['trend']]
    stop_price = avg_cost * (1 - r['stop'])

    if action == 'BUY':
        summary = (f"The bot {'added to' if reason == 'top_up' else 'bought'} {a['name']} ({a['ticker']}) because it ranked #{a['rank']} of {len(A)} "
                   f"investments for your {risk_word}-risk, {plan} plan, with a score of {a['score']:.2f} out of 1."
                   + (' Your position had fallen below its target share, so the bot topped it up.' if reason == 'top_up' else ''))
    else:
        summary = {'stop': f"The bot sold {a['name']} ({a['ticker']}) because its price fell {abs(m['price'] / avg_cost - 1):.1%} below the average price paid, "
                           f"reaching the {r['stop']:.0%} loss limit for {risk_word} risk.",
                   'dropped': f"The bot sold {a['name']} ({a['ticker']}) because it no longer fits the plan: "
                              + ('; '.join(a['blockers']) if a['blockers'] else 'other investments now score higher') + '.',
                   'trim': f"The bot sold part of {a['name']} ({a['ticker']}) because it grew above its target share of your portfolio. "
                           'Trimming keeps one investment from carrying too much of the risk.',
                   'withdraw': f"The bot sold part of {a['name']} ({a['ticker']}) to free up virtual cash because you lowered the investment amount.",
                   'reset': f"The bot sold all of {a['name']} ({a['ticker']}) because you chose to start the portfolio over."}[reason]

    rsi = m['rsi']
    indicators = ('RSI was not available.' if rsi is None else f'RSI (a 0–100 gauge of recent buying vs selling) was {rsi:.0f}: ' + (
        'oversold — it fell a lot recently; sometimes a bounce follows, sometimes the drop continues.' if rsi < 30 else
        'overbought — it rose a lot recently; a pause or pullback is common.' if rsi > 70 else 'neutral — not stretched in either direction.'))
    avgs = [(w_, m[f'sma{w_}']) for w_ in (20, 50, 200) if m[f'sma{w_}']]
    if avgs:
        indicators += f" The price ({_usd(m['price'])}) was " + ', '.join(f"{'above' if m['price'] > v else 'below'} its {w_}-day average ({_usd(v)})" for w_, v in avgs) \
                      + '. Staying above these averages usually means the trend is up.'
    movement = (f"Past week {_pc(m['w1'])}, past month {_pc(m['m1'])}, past 3 months {_pc(m['m3'])}, past 6 months {_pc(m['m6'])}, past year {_pc(m['m12'])}."
                + (f" It was {1 - m['price'] / m['high52']:.1%} below its 52-week high of {_usd(m['high52'])} and {m['price'] / m['low52'] - 1:.1%} above its 52-week low of {_usd(m['low52'])}."
                   if m['high52'] and m['low52'] else ''))
    volatility = (f"About {vol:.0%} a year. In a typical month its price might move up or down by around {month_move:.1%}. "
                  f"Its worst drop from a high in the past year was {abs(m['max_drawdown'] or 0):.1%}." if m['vol'] else 'There was not enough history to measure volatility.')

    risks = [KIND_RISK[a['kind']]]
    if vol > 0.35: risks.append('Its price swings a lot, so short-term losses can be large.')
    if rsi is not None and rsi > 70: risks.append('It rose quickly recently, which is often followed by a pullback.')
    if m['high52'] and m['price'] >= 0.97 * m['high52']: risks.append('It was near its 52-week high, so there is little recent cushion.')
    if any(i['tone'] == 'negative' for i in a['news']): risks.append('Some recent headlines about it were negative.')
    if reg['risk_off']: risks.append('The overall market was in a downtrend.')
    risks.append('Past price patterns do not reliably predict future prices.')

    weights = a.get('weights') or tf['weights']  # the weights this asset was actually scored with
    strengths = sorted((k for k in weights if weights[k] > 0 and (k != 'news' or a['components']['news'] > 0.55)), key=lambda k: -weights[k] * a['components'][k])[:2]
    alternatives = []
    others = [t for t in analysis['ranked'] if t != a['ticker']]
    # Mostly the best options it passed over (the informative comparison), plus the top one it also holds.
    compared = [t for t in others if t not in analysis['targets']][:3] + [t for t in others if t in analysis['targets']][:1]
    for t in sorted(compared, key=lambda t: -A[t]['score']):
        o = A[t]; held = t in analysis['targets']
        alternatives.append({'ticker': t, 'name': o['name'], 'score': round(o['score'], 3), 'status': 'Also in the plan' if held else 'Not chosen',
                             'reason': 'It is also part of the plan.' if held else ((o['blockers'][0][0].upper() + o['blockers'][0][1:] + '.') if o['blockers']
                                       else f"It scored lower, and a {risk_word}-risk plan holds at most {r['picks']} investments.")})
    if action == 'BUY':
        why_asset = (f"The bot scored all {len(A)} investments it follows. {a['name']} scored {a['score']:.2f} (rank #{a['rank']}) and passed every check "
                     f"for {risk_word} risk. It did best on {' and '.join(COMPONENT_LABEL[k] for k in strengths)}. "
                     + (f"Its business: {a['holds']}." if a['kind'] == 'stock' else f"It holds {a['holds']}."))
    else:
        why_asset = f"At this point {a['name']} scored {a['score']:.2f} (rank #{a['rank']} of {len(A)}). " + {
            'stop': 'Selling was triggered by the loss limit, not by its score.',
            'withdraw': 'This sale was caused by your settings change, not by the analysis.',
            'reset': 'This sale was caused by starting over, not by the analysis.'}.get(reason, 'The investments listed below were compared at the same time.')

    if action == 'BUY':
        sizing = 'its score divided by its volatility, so steadier investments get more money' if settings['risk'] != 'high' else 'its score (high risk does not favor steadier investments)'
        why_amount = (f"The plan gives {a['ticker']} a target of {target:.0%} of your portfolio (about {_usd(target * portfolio_value)} of {_usd(portfolio_value)}). "
                      f"Each target comes from {sizing}. No single investment can exceed {r['max_weight']:.0%}, individual company stocks together are capped at {r['stock_share']:.0%}"
                      + (f", and crypto together is capped at {r['crypto_share']:.0%} because its prices swing so much" if a['kind'] == 'crypto' else
                         f", and one industry ({a['sector']}) is capped at {r['sector_cap']:.0%} so a single industry’s bad news can’t sink the whole portfolio" if a.get('sector') and a['sector'] not in DIVERSIFIED else '')
                      + '. '
                      f"About {analysis['cash_reserve']:.0%} stays in cash for {risk_word} risk"
                      + (' (more than usual because the market was in a downtrend)' if reg['risk_off'] and settings['risk'] != 'high' else '')
                      + f". This trade used {_usd(value)}.")
        downside = (f"No outcome is certain. Based on recent volatility, a bad month (roughly 1 in 20) could mean a drop of about {1.65 * month_move:.1%} — "
                    f"around {_usd(1.65 * month_move * value)} on this {_usd(value)} trade — and bigger drops are possible. The loss limit would sell near "
                    f"{_usd(stop_price)} ({r['stop']:.0%} below the average price paid), but prices can jump past that level.")
    else:
        why_amount = {'trim': f"It was worth more than its {target:.0%} target, so the bot sold {_usd(value)} to bring it back near the target.",
                      'stop': 'The loss limit sells the whole position at once.',
                      'dropped': 'Investments that no longer fit the plan are sold completely.',
                      'withdraw': 'The bot sold the same share of every investment, so the portfolio stays balanced while raising the cash you asked to take out.',
                      'reset': 'Starting over sells every investment completely.'}[reason] + f' The {_usd(value)} went back into your virtual cash.'
        downside = 'Selling removes this investment’s risk, but if its price rises afterward the portfolio will miss that gain.'

    return {
        'summary': summary, 'market': reg['text'],
        'news': [{k: i.get(k) for k in ('title', 'url', 'source', 'published_at', 'tone')} for i in a['news']],
        'news_note': ((f"Recent headlines make up about {a['news_weighted']:.0%} of this score, and newer ones count more. " if a.get('news_weighted') else 'Headlines only nudge the score a little. ') + 'Their tone is judged by simple keyword matching, which can misread a headline.' if a['news'] else
                      'No recent headlines about this investment were found in the sources checked (Yahoo Finance, BBC, The Guardian, CNBC). News was treated as neutral.'),
        'price_movement': movement, 'indicators': indicators, 'fundamentals': a['fundamentals_text'], 'volatility': volatility,
        'risk_factors': risks, 'why_asset': why_asset, 'alternatives': alternatives, 'why_amount': why_amount,
        'holding_period': ((f"You chose to invest for {settings['months']} month{'s' if settings['months'] != 1 else ''}, so the bot uses its {plan} rules and expects to hold "
                            if settings.get('months') else f'For a {plan} plan the bot expects to hold ')
                           + f"investments for {tf['holding']}. It can sell sooner if a sell condition is met; there is no fixed date."
                           if action == 'BUY' else 'This position is now closed' + (' (part of it is still held).' if reason in ('trim', 'withdraw') else '.')),
        'downside': downside,
        'sell_conditions': [f"The price falls to about {_usd(stop_price)} (the {r['stop']:.0%} loss limit).",
                            f'The price drops below its {days}-day average, a sign the trend has turned down.',
                            f"Its score falls below {MIN_SCORE:.2f} or other investments rank higher at a review.",
                            f"Its volatility rises above the {r['max_vol']:.0%} limit for {risk_word} risk.",
                            'It grows well above its target share (the bot trims it back).'],
        'strategy_change': [f'Every {REVIEW_MINUTES} minutes, day and night, the bot re-scores everything with fresh prices, fundamentals and headlines. Stocks and ETFs only trade while the US market is open; crypto trades 24/7.',
                            'If the S&P 500 drops below its 200-day average and falls more than 5% in a month, the bot keeps 15% more in cash (low and medium risk).',
                            'If you change the amount, risk level or timeframe, the bot rebuilds the plan from scratch.',
                            'Big news, earnings surprises or sharp price moves change the scores and can change what it holds.'],
        'score': {'total': round(a['score'], 3), 'components': {COMPONENT_LABEL[k]: round(a['components'][k], 3) for k in weights if weights[k] > 0},
                  'weights': {COMPONENT_LABEL[k]: weights[k] for k in weights if weights[k] > 0}},
        'price_note': price_note(now, m['date'], a['kind']), 'disclaimer': DISCLAIMER,
    }


class PortfolioBot:
    def __init__(self, state_dir, market=None, universe=None, clock=None, market_open=None):
        self.dir = Path(state_dir); self.file = self.dir / 'portfolio.json'; self.lock = self.dir / 'portfolio.lock'
        self.market = market or YahooMarket(); self.universe = universe or UNIVERSE
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.market_open = market_open or us_market_open

    def _read(self):
        if not self.file.exists():
            return None
        s = json.loads(self.file.read_text())
        if s.get('mode') != 'paper':
            raise RuntimeError('Live execution is unsupported')
        s['settings'].setdefault('months', {'short': 2, 'medium': 6, 'long': 24}[s['settings']['timeframe']])  # older saves
        s.setdefault('deposits', s['settings']['amount'])
        return s

    def _analysis(self, s):
        tickers = list(self.universe)
        history = self.market.history(tickers)
        fundamentals = self.market.fundamentals(tickers)
        headlines = self.market.headlines()
        held = set(s['holdings'])
        first = analyze(history, fundamentals, {}, headlines, s['settings']['risk'], s['settings']['timeframe'], self.universe, held)
        watch = set(first['ranked'][:10]) | set(s['holdings'])  # per-ticker news only where it can matter
        news = {t: self.market.news(t) for t in watch}
        return analyze(history, fundamentals, news, headlines, s['settings']['risk'], s['settings']['timeframe'], self.universe, held)

    def _value(self, s, prices):
        return s['cash'] + sum(h['shares'] * prices.get(t, h['avg_cost']) for t, h in s['holdings'].items())

    def _trade(self, s, action, a, shares, analysis, reason, now, prices):
        t = a['ticker']; market_price = prices[t]
        shares = math.floor(shares * 1e6) / 1e6
        h = s['holdings'].get(t)
        if action == 'SELL':
            shares = min(shares, h['shares'])
        if shares <= 0:
            return None
        price = market_price * (1 + SLIPPAGE if action == 'BUY' else 1 - SLIPPAGE)
        value = shares * price; cash_before = s['cash']; pv_before = self._value(s, prices)
        avg_cost = h['avg_cost'] if h else price; realized = None
        if action == 'BUY':
            s['cash'] -= value
            if h:
                total = h['shares'] + shares; h['avg_cost'] = (h['shares'] * h['avg_cost'] + value) / total; h['shares'] = total
            else:
                s['holdings'][t] = {'shares': shares, 'avg_cost': price, 'opened_at': _iso(now), 'name': a['name'], 'kind': a['kind']}
            avg_cost = s['holdings'][t]['avg_cost']
        else:
            realized = shares * (price - h['avg_cost']); s['cash'] += value; s['realized_pnl'] += realized; h['shares'] -= shares
            if h['shares'] < 1e-6:
                del s['holdings'][t]
        record = {'id': f"TR{len(s['trades']) + 1}", 'time': _iso(now), 'ticker': t, 'name': a['name'], 'kind': a['kind'], 'action': action,
                  'shares': shares, 'price': price, 'market_price': market_price, 'value': value,
                  'cash_before': cash_before, 'cash_after': s['cash'], 'portfolio_before': pv_before, 'portfolio_after': self._value(s, prices),
                  'realized_pnl': realized, 'reason': reason, 'simulated': True,
                  'explanation': explain(action, reason, a, analysis, s['settings'], pv_before, value, avg_cost, now)}
        s['trades'].append(record)
        return record

    def _rebalance(self, s, now, stops_only=False):
        analysis = self._analysis(s)
        A = analysis['assets']; prices = {t: a['metrics']['price'] for t, a in A.items()}
        r = RISK[s['settings']['risk']]; made = []
        market_open = self.market_open(now)
        tradable = lambda t: market_open or A[t]['kind'] == 'crypto'  # stocks/ETFs only fill while the US market is open
        for t, h in list(s['holdings'].items()):
            if t not in A or not tradable(t):
                continue  # no price data or market closed: never trade on a price that can't fill
            if prices[t] <= h['avg_cost'] * (1 - r['stop']):
                made.append(self._trade(s, 'SELL', A[t], h['shares'], analysis, 'stop', now, prices))
            elif not stops_only and t not in analysis['targets']:
                made.append(self._trade(s, 'SELL', A[t], h['shares'], analysis, 'dropped', now, prices))
        if not stops_only:
            pv = self._value(s, prices)
            for t, weight in analysis['targets'].items():
                h = s['holdings'].get(t)
                excess = h['shares'] * prices[t] - weight * pv if h else 0.
                if excess > max(TRIM_BAND * pv, MIN_TRADE) and tradable(t):
                    made.append(self._trade(s, 'SELL', A[t], excess / prices[t], analysis, 'trim', now, prices))
            pv = self._value(s, prices)
            reserve = analysis['cash_reserve'] * pv  # holdings may sit slightly above target (trim band), so buys must never eat the cash reserve
            for t, weight in sorted(analysis['targets'].items(), key=lambda x: -x[1]):
                h = s['holdings'].get(t)
                want = weight * pv - (h['shares'] * prices[t] if h else 0.)
                spend = min(want, s['cash'] - reserve - 0.01)
                if want > (max(TRIM_BAND * pv, MIN_TRADE) if h else MIN_TRADE) and spend >= MIN_TRADE and tradable(t):
                    made.append(self._trade(s, 'BUY', A[t], spend / (prices[t] * (1 + SLIPPAGE)), analysis, 'top_up' if h else 'new', now, prices))
            s['last_rebalance'] = _iso(now)
            s['strategy'] = self._strategy(analysis, s, now)
        made = [x for x in made if x]
        if s.get('market_open') is not None and s['market_open'] != market_open:
            s['activity'].append({'time': _iso(now), 'text': 'The US stock market opened. Stocks and ETFs can trade again.' if market_open
                                  else 'The US stock market closed. Stock and ETF trades wait for the next open; crypto keeps trading 24/7.'})
        s['market_open'] = market_open
        if made:
            s['activity'].append({'time': _iso(now), 'text': f"Reviewed {len(A)} investments and made {len(made)} simulated trade{'s' if len(made) != 1 else ''}."})
        elif not stops_only:
            note = f'Reviewed {len(A)} investments. No trades needed' + ('.' if market_open else ' — stock and ETF trades wait for the US market to open.')
            if not s['activity'] or s['activity'][-1]['text'] != note:  # don't repeat the same line every 15 minutes
                s['activity'].append({'time': _iso(now), 'text': note})
        s['activity'] = s['activity'][-200:]
        s['last_checked'] = _iso(now)
        s['prices_date'] = A['SPY']['metrics']['date'] if 'SPY' in A else None
        self._point(s, now, prices, [x['id'] for x in made])

    def _strategy(self, analysis, s, now):
        r, tf = RISK[s['settings']['risk']], TIMEFRAME[s['settings']['timeframe']]; A = analysis['assets']
        targets = sorted(analysis['targets'].items(), key=lambda x: -x[1])
        text = tf['focus'] if targets else f"None of the {len(A)} investments passed the checks at the last review, so the bot is holding cash."
        return {'summary': text, 'method': METHOD, 'market': analysis['regime']['text'], 'regime': analysis['regime']['label'],
                'targets': [{'ticker': t, 'name': A[t]['name'], 'weight': w, 'score': round(A[t]['score'], 3)} for t, w in targets],
                'cash_reserve': 1 - sum(analysis['targets'].values()), 'review_every': f'{REVIEW_MINUTES} minutes', 'reviewed_at': _iso(now)}

    def _point(self, s, now, prices, trade_ids):
        s['prices'] = {**s.get('prices', {}), **prices}
        value = self._value(s, prices)
        day = now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
        if (s.get('day') or {}).get('key') != day:
            s['day'] = {'key': day, 'base': value}
        point = {'time': _iso(now), 'value': value, 'cash': s['cash'], 'deposits': s['deposits'], 'trades': trade_ids}
        hist = s['equity_history']
        if hist and not trade_ids and not hist[-1]['trades'] and (now - datetime.fromisoformat(hist[-1]['time'])).total_seconds() < 60:
            hist[-1] = point
        else:
            hist.append(point)
        if len(hist) > 6000:  # thin points older than two days to one per hour; trade points are always kept
            cutoff, kept, last_hour = now - timedelta(days=2), [], None
            for pt in hist:
                if pt['trades'] or datetime.fromisoformat(pt['time']) >= cutoff or pt['time'][:13] != last_hour:
                    kept.append(pt)
                    last_hour = pt['time'][:13]
            hist = kept[-6000:]
        s['equity_history'] = hist

    def setup(self, amount, risk, months):
        _validate(amount, risk, months)
        with locked(self.lock):
            now = self.clock()
            s = {'mode': 'paper', 'simulated': True, 'enabled': True,
                 'settings': {'amount': float(amount), 'risk': risk, 'months': months, 'timeframe': timeframe_for(months)}, 'deposits': float(amount),
                 'created_at': _iso(now), 'cash': float(amount), 'holdings': {}, 'trades': [], 'realized_pnl': 0., 'equity_history': [],
                 'activity': [{'time': _iso(now), 'text': f"Started the AI bot with {_usd(amount)} of virtual money ({RISK[risk]['label'].lower()} risk, {months} month{'s' if months != 1 else ''})."}],
                 'day': None, 'last_rebalance': None, 'strategy': None, 'prices': {}}
            self._rebalance(s, now)  # raises RuntimeError before anything is saved if market data is unavailable
            atomic_json(self.file, s)
            return self.public(s)

    def update_settings(self, amount, risk, months, confirm=False, reset=False):
        """Apply a new amount, risk level or period to a running portfolio. Trading history is always kept."""
        _validate(amount, risk, months)
        amount = float(amount)
        with locked(self.lock):
            s = self._read()
            if s is None:
                raise ValueError('Start the AI bot first.')
            reduction = s['deposits'] - amount
            estimate = self._value(s, s.get('prices', {}))
            # Ask for confirmation before touching market data or the portfolio.
            if reset and not confirm:
                raise ConfirmationRequired(f'Starting over sells every investment and restarts this simulated portfolio at {_usd(amount)}, '
                                           'with profit and loss back at $0. Your trading history is kept.')
            if not reset and reduction > 0.005:
                if reduction > estimate - 0.01:
                    raise ValueError(f"Your portfolio is worth about {_usd(estimate)}, so the amount can't be lowered by {_usd(reduction)}. Lower it by less, or start over.")
                if not confirm:
                    raise ConfirmationRequired(f'Lowering the amount takes {_usd(reduction)} out of this simulated portfolio'
                                               + (f", selling about {_usd(reduction - s['cash'])} of investments because cash only covers {_usd(s['cash'])}" if reduction > s['cash'] else '')
                                               + '. Your trading history is kept.')
            now = self.clock()
            analysis = self._analysis(s)
            A = analysis['assets']; prices = {t: a['metrics']['price'] for t, a in A.items()}
            value = self._value(s, prices); old = dict(s['settings']); made = []
            if reset:
                result = value - s['deposits']
                for t, h in list(s['holdings'].items()):
                    if t in A:
                        made.append(self._trade(s, 'SELL', A[t], h['shares'], analysis, 'reset', now, prices))
                if s['holdings']:
                    raise RuntimeError('Some investments have no current price')  # nothing is saved
                s.update(cash=amount, deposits=amount, realized_pnl=0., day=None)
                s['activity'].append({'time': _iso(now), 'text': f"You started over with {_usd(amount)}. The previous portfolio ended at {_usd(value)} "
                                                                  f"({'+' if result >= 0 else '−'}{_usd(abs(result))})."})
            elif reduction > 0.005:
                if reduction > value - 0.01:
                    raise ValueError(f"Your portfolio is worth {_usd(value)}, so the amount can't be lowered by {_usd(reduction)}.")
                short = reduction - s['cash']
                if short > 0:
                    held = sum(h['shares'] * prices[t] for t, h in s['holdings'].items() if t in prices)
                    fraction = 1. if held <= short * 1.001 else short * 1.001 / held  # small buffer covers the simulated price difference
                    for t, h in list(s['holdings'].items()):
                        if t in A:
                            made.append(self._trade(s, 'SELL', A[t], h['shares'] * fraction, analysis, 'withdraw', now, prices))
                s['cash'] = max(0., s['cash'] - reduction); s['deposits'] = amount
                s['activity'].append({'time': _iso(now), 'text': f"You lowered the investment amount by {_usd(reduction)}; it was taken out of virtual cash"
                                                                  + (' after selling part of each investment.' if short > 0 else '.')})
            elif reduction < -0.005:
                s['cash'] -= reduction; s['deposits'] = amount
                s['activity'].append({'time': _iso(now), 'text': f'You raised the investment amount by {_usd(-reduction)}; it was added to virtual cash.'})
            changes = []
            if risk != old['risk']:
                changes.append(f"risk {RISK[old['risk']]['label']} → {RISK[risk]['label']}")
            if months != old['months']:
                changes.append(f"period {old['months']} → {months} months")
            s['settings'].update(amount=amount, risk=risk, months=months, timeframe=timeframe_for(months))
            if changes:
                s['activity'].append({'time': _iso(now), 'text': 'You changed the settings: ' + ', '.join(changes) + '.'})
            made = [x for x in made if x]
            if made:
                self._point(s, now, prices, [x['id'] for x in made])
            if s['enabled']:
                self._rebalance(s, now)  # apply the new plan right away
            else:
                self._point(s, now, prices, [])
            s.pop('error', None)
            atomic_json(self.file, s)
            return self.public(s)

    def backfill(self, amount, risk, months, days=30, confirm=False):
        """Start as if the bot had been trading for the past `days`: replay real daily closing prices, then continue live."""
        _validate(amount, risk, months)
        if isinstance(days, bool) or not isinstance(days, int) or not 5 <= days <= 90:
            raise ValueError('Choose between 5 and 90 days to replay.')
        if self.file.exists() and not confirm:
            raise ConfirmationRequired(f'Replaying the past {days} days replaces your current simulated portfolio and its trading history with a fresh replay.')
        now = self.clock()
        intraday = None
        if hasattr(self.market, 'intraday'):
            try:
                intraday = self.market.intraday(list(self.universe))
            except RuntimeError:
                intraday = None  # fall back to one review per day at the close
            covered = sum(1 for t in self.universe if (intraday or {}).get(t, {}).get('times'))
            if intraday is not None and (not intraday.get('SPY', {}).get('times') or covered < 0.8 * len(self.universe)):
                intraday = None  # incomplete hourly prices: replay once per day rather than pretend to be hourly
        replay = HistoricalMarket(self.market, {t for t, u in self.universe.items() if u[1] == 'crypto'}, intraday)
        full = self.market.history(list(self.universe))
        trading_days = set(full['SPY']['dates']) if 'SPY' in full else None  # real trading days, so market holidays are skipped

        def replay_open(t):
            ny = t.astimezone(NY)
            if trading_days is not None and ny.date().isoformat() not in trading_days:
                return False
            return (10, 30) <= (ny.hour, ny.minute) <= (15, 30) if intraday else True  # hourly: only after a finished in-session bar
        moment = {}
        bot = PortfolioBot(self.dir, replay, self.universe, clock=lambda: moment['now'], market_open=replay_open)
        bot._replaying = True
        marker = self.dir / 'replay.lock'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(_iso(now))
        start = (now - timedelta(days=days)).astimezone(NY).date()
        while start.weekday() >= 5:
            start += timedelta(days=1)
        try:
            steps = 0
            if intraday:
                at = datetime(start.year, start.month, start.day, 10, 30, tzinfo=NY).astimezone(timezone.utc)  # first finished hourly bar
                step = timedelta(hours=1)
            else:
                at = datetime(start.year, start.month, start.day, 16, 0, tzinfo=NY).astimezone(timezone.utc)  # each day's US market close
                step = timedelta(days=1)
            while at <= now - timedelta(minutes=REVIEW_MINUTES):
                moment['now'] = replay.as_of = at
                if steps == 0:
                    bot.setup(amount, risk, months)
                else:
                    bot.refresh()
                steps += 1
                at += step
            if steps < 2:
                raise ValueError('There are not enough past days to replay.')
            with locked(self.lock):
                s = self._read()
                for trade in s['trades']:
                    trade['replayed'] = True
                    trade['explanation']['price_note'] = (
                        f"Replayed trade: the bot wasn't running on {trade['time'][:10]}, so this shows what it would have done with {'that hour' if intraday else 'that day'}'s real prices. "
                        "Company fundamentals are today's figures, and only headlines published before the trade were used.")
                s['replay'] = {'start': start.isoformat(), 'end': _iso(moment['now']), 'days': days, 'resolution': 'hourly' if intraday else 'daily'}
                s['activity'].append({'time': _iso(moment['now']), 'text': f'Finished replaying the past {days} days with real prices. The bot now keeps trading live.'})
                atomic_json(self.file, s)
        finally:
            marker.unlink(missing_ok=True)
        return self.refresh()  # first live review, with today's prices

    def refresh(self, allow_trades=True):
        with locked(self.lock):
            s = self._read()
            if s is None:
                return self.public(None)
            marker = self.dir / 'replay.lock'
            if not getattr(self, '_replaying', False) and marker.exists() and time.time() - marker.stat().st_mtime < 900:
                return self.public(s)  # a past-month replay is being written; don't interleave live reviews
            now = self.clock()
            try:
                due = s['last_rebalance'] is None or now - datetime.fromisoformat(s['last_rebalance']) >= timedelta(minutes=REVIEW_MINUTES)
                if s['enabled'] and allow_trades and due:
                    self._rebalance(s, now)
                else:
                    history = self.market.history(list(self.universe))
                    prices = {t: float(v['close'][-1]) for t, v in history.items()}
                    stop = RISK[s['settings']['risk']]['stop']
                    open_now = self.market_open(now)
                    if s['enabled'] and allow_trades and any(t in prices and prices[t] <= h['avg_cost'] * (1 - stop) and (open_now or h.get('kind') == 'crypto')
                                                             for t, h in s['holdings'].items()):
                        self._rebalance(s, now, stops_only=True)  # full analysis so the sale is explained
                    else:
                        self._point(s, now, prices, [])
                        s['last_checked'] = _iso(now)
                s.pop('error', None)
            except RuntimeError:
                s['error'] = 'Market data is unavailable right now. No trades were made; the bot will try again automatically.'
            atomic_json(self.file, s)
            return self.public(s)

    def control(self, action):
        with locked(self.lock):
            s = self._read()
            if s is None:
                raise ValueError('Set up the bot first.')
            now = self.clock()
            if action in ('pause', 'resume'):
                s['enabled'] = action == 'resume'
                s['activity'].append({'time': _iso(now), 'text': 'You paused the bot. It will not trade until you resume it.' if action == 'pause' else 'You resumed the bot.'})
            elif action == 'review':
                self._rebalance(s, now)
            else:
                raise ValueError('Unknown action')
            atomic_json(self.file, s)
            return self.public(s)

    def public(self, s):
        if s is None:
            return {'configured': False, 'simulated': True,
                    'risk_levels': {k: v['label'] for k, v in RISK.items()}, 'timeframes': {k: {'label': v['label'], 'holding': v['holding'], 'review': v['review']} for k, v in TIMEFRAME.items()}}
        prices = s.get('prices', {}); holdings = []; value_sum = cost_sum = 0.
        for t, h in s['holdings'].items():
            price = prices.get(t, h['avg_cost']); v = h['shares'] * price; cost = h['shares'] * h['avg_cost']
            value_sum += v; cost_sum += cost
            holdings.append({'ticker': t, 'name': h['name'], 'kind': h['kind'], 'shares': h['shares'], 'avg_cost': h['avg_cost'], 'price': price,
                             'value': v, 'cost': cost, 'unrealized_pnl': v - cost, 'unrealized_pct': price / h['avg_cost'] - 1, 'opened_at': h['opened_at']})
        total = s['cash'] + value_sum; amount = s['deposits']  # profit/loss is measured against the money put in
        for h in holdings:
            h['weight'] = h['value'] / total if total else 0.
        holdings.sort(key=lambda h: -h['value'])
        base = (s.get('day') or {}).get('base') or total
        tf = TIMEFRAME[s['settings']['timeframe']]
        next_review = (datetime.fromisoformat(s['last_rebalance']) + timedelta(minutes=REVIEW_MINUTES)).isoformat() if s['last_rebalance'] else None
        now = self.clock()
        trades = []
        for t in s['trades'][-1000:]:
            if t['action'] == 'SELL':
                pnl, kind = t['realized_pnl'], 'realized'
            elif t['ticker'] in s['holdings'] and t['ticker'] in prices:
                pnl, kind = t['shares'] * (prices[t['ticker']] - t['price']), 'unrealized'
            else:
                pnl, kind = None, 'closed'
            trades.append({**t, 'pnl': pnl, 'pnl_type': kind})
        status = 'paused' if not s['enabled'] else ('waiting' if s.get('error') else ('holding' if holdings else 'cash'))
        return {'configured': True, 'simulated': True, 'enabled': s['enabled'], 'status': status, 'created_at': s['created_at'], 'deposits': amount,
                'settings': {**s['settings'], 'risk_label': RISK[s['settings']['risk']]['label'], 'timeframe_label': tf['label'], 'holding': tf['holding']},
                'cash': s['cash'], 'invested': cost_sum, 'holdings_value': value_sum, 'portfolio_value': total,
                'total_return': total - amount, 'total_return_pct': total / amount - 1, 'daily_return': total - base, 'daily_return_pct': total / base - 1 if base else 0.,
                'realized_pnl': s['realized_pnl'], 'unrealized_pnl': value_sum - cost_sum, 'holdings': holdings,
                'allocation': [{'ticker': h['ticker'], 'name': h['name'], 'weight': h['weight']} for h in holdings] + [{'ticker': 'CASH', 'name': 'Virtual cash', 'weight': s['cash'] / total if total else 1.}],
                'strategy': s['strategy'], 'trades': trades, 'activity': s['activity'], 'equity_history': s['equity_history'],
                'last_rebalance': s['last_rebalance'], 'next_review': next_review, 'last_checked': s.get('last_checked') or s['last_rebalance'],
                'review_minutes': REVIEW_MINUTES, 'replay': s.get('replay'), 'market_open': self.market_open(now), 'next_market_open': next_market_open(now).isoformat(), 'error': s.get('error'),
                'price_note': price_note(now, s.get('prices_date') or 'the last trading day'), 'disclaimer': DISCLAIMER}
