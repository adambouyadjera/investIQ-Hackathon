"""Simulator: a personalized stock & ETF plan for a one-time and monthly amount, with projections.

Uses the AI bot's analysis (live prices, fundamentals, news, trends, indicators, volatility) and risk limits.
Everything here is an educational estimate: projections use simple long-run assumptions, never guarantees.
"""
from __future__ import annotations
import bisect, calendar, json, math, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from .paper import ROOT, locked, atomic_json
from .portfolio_bot import (YahooMarket, HistoricalMarket, UNIVERSE, RISK, SECTORS, DIVERSIFIED, COMPONENT_LABEL, TIMEFRAME, NY,
                            analyze, explain, timeframe_for, price_note, _usd, NEWS_MEMORY)

SIM_UNIVERSE = {t: u for t, u in UNIVERSE.items() if u[1] != 'crypto'}  # stocks and ETFs only
# Long-run planning assumptions for a diversified mix at each risk level. Deliberately modest; not forecasts.
EXPECTED_RETURN = {'low': 0.04, 'medium': 0.06, 'high': 0.08}
# Lower risk leans on broad, diversified funds (whole-market, international and bond funds), not single-industry funds.
DIVERSIFIED_FLOOR = {'low': 0.60, 'medium': 0.35, 'high': 0.0}
# A whole-market or bond fund already holds hundreds of companies, so it may take a bigger share than one stock or sector fund.
DIVERSIFIED_MAX = {'low': 0.35, 'medium': 0.35, 'high': 0.35}


def cap_for(ticker, r, risk):
    return max(r['max_weight'], DIVERSIFIED_MAX[risk]) if SECTORS.get(ticker) in DIVERSIFIED else r['max_weight']
PROJECTION_NOTE = ('Projections are estimates, not predictions. They assume a steady long-run yearly return for your risk level '
                   '(expected line) and use this mix’s recent volatility for the optimistic and pessimistic lines, which show a '
                   'roughly 1-in-10 better or worse outcome. Real results can fall outside this range, including losses.')
# Simulator recommendations lean on the latest news: its share of each score, and how often headlines are re-checked.
NEWS_WEIGHT, NEWS_TTL = 0.35, 600
# Live mode: every minute re-check this many stocks' Yahoo headlines (oldest first), so each stock is re-checked every few
# minutes without flooding Yahoo with requests. Rankings being watched are recomputed after each check.
LIVE_ROTATION, LIVE_WATCH_SECONDS, LIVE_EVENTS = 5, 600, 20
_live_lock, _live = threading.Lock(), {}


def live_market(market):
    if market is None:
        market = YahooMarket(); market.news_ttl = NEWS_TTL
    return market


def _when(item):
    try:
        dt = datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
    except (TypeError, ValueError, AttributeError, KeyError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class NewsArchive:
    """Every headline InvestIQ has fetched, per stock. Yahoo only returns the latest ten or so, so without this,
    older news would disappear from the scores as soon as newer stories push it out."""
    def __init__(self, path=None, keep_days=400, per_ticker=300):
        self.path, self.keep_days, self.per_ticker = Path(path or ROOT / 'state/news-archive.json'), keep_days, per_ticker

    def merge(self, fetched, now):
        with locked(self.path.with_suffix('.lock')):
            try:
                data = json.loads(self.path.read_text())
            except (OSError, ValueError):
                data = {}
            cutoff, out = now - timedelta(days=self.keep_days), {}
            for t, items in fetched.items():
                known = {i['url']: i for i in data.get(t, [])}
                for i in items:
                    if i.get('url') and _when(i):
                        known.setdefault(i['url'], {k: i.get(k) for k in ('title', 'url', 'source', 'published_at')})
                data[t] = sorted((i for i in known.values() if _when(i) and _when(i) >= cutoff), key=_when, reverse=True)[:self.per_ticker]
                out[t] = data[t] + [i for i in items if not _when(i)]
            atomic_json(self.path, data)
        return out


def latest_news(market, tickers, archive=None, now=None):
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(zip(tickers, pool.map(market.news, tickers)))
    return archive.merge(fetched, now or datetime.now(timezone.utc)) if archive else fetched


DISCLAIMER = 'Educational simulation with no real money. Not financial advice, and no result is guaranteed.'


def validate(initial, monthly, risk, months):
    for value, name, top in ((initial, 'one-time investment', 1_000_000), (monthly, 'monthly investment', 100_000)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= top:
            raise ValueError(f'Choose a {name} between $0 and {_usd(top)}.')
    if initial + monthly <= 0:
        raise ValueError('Enter a one-time or monthly investment amount.')
    if risk not in RISK:
        raise ValueError('Choose Low, Medium or High risk.')
    if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 120:
        raise ValueError('Choose an investment period between 1 and 120 months.')


def round_to_total(values, total, step):
    """Round each value to `step` so the rounded values add up exactly to `total` (largest-remainder method)."""
    units = round(total / step)
    raw = [round(v / step, 6) for v in values]
    floors = [math.floor(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)[:max(0, units - sum(floors))]:
        floors[i] += 1
    return [round(f * step, 2) for f in floors]


def fill_weights(picks, r, risk):
    """Share 100% across picks: score (÷ volatility below high risk), then per-asset, stock and industry limits.
    Money trimmed by a limit is re-shared among picks that still have room. Returns (weights, share left over)."""
    raw = {a['ticker']: max(1e-6, a['score'] if risk == 'high' else a['score'] / max(a['metrics']['vol'] or 0.2, 0.05)) for a in picks}
    kind = {a['ticker']: a['kind'] for a in picks}
    weights, free, left = dict.fromkeys(raw, 0.), set(raw), 1.0
    for _ in range(100):
        if left <= 1e-9 or not free:
            break
        total = sum(raw[t] for t in free)
        for t in free:
            weights[t] += left * raw[t] / total
        left = 0.
        for t in list(free):
            cap = cap_for(t, r, risk)
            if weights[t] > cap + 1e-9:
                left += weights[t] - cap; weights[t] = cap; free.discard(t)
        groups = [([t for t in raw if kind[t] == 'stock'], r['stock_share'])]
        groups += [([t for t in raw if SECTORS.get(t) == sector], r['sector_cap']) for sector in {SECTORS.get(t) for t in raw} - DIVERSIFIED - {None}]
        for members, limit in groups:
            share = sum(weights[t] for t in members)
            if share > limit + 1e-9:
                for t in members:
                    weights[t] *= limit / share
                left += share - limit; free.difference_update(members)
    return weights, left


def apply_floor(weights, r, risk, floor):
    """Raise the diversified-fund share to `floor` (within each fund's own limit), taking it proportionally from the rest."""
    funds = [t for t in weights if SECTORS.get(t) in DIVERSIFIED]
    share = sum(weights[t] for t in funds)
    rooms = {t: max(0., cap_for(t, r, risk) - weights[t]) for t in funds}
    add = min(max(0., floor - share), sum(rooms.values()))
    others = [t for t in weights if t not in funds]
    rest = sum(weights[t] for t in others)
    if add <= 1e-9 or rest <= 1e-9:
        return weights
    add = min(add, rest)
    total_room = sum(rooms.values())
    for t in funds:
        weights[t] += add * rooms[t] / total_room
    for t in others:
        weights[t] *= (rest - add) / rest  # scaling down never breaks a limit
    return weights


def choose(analysis, risk, include=()):
    r, A = RISK[risk], analysis['assets']
    eligible = [A[t] for t in analysis['ranked'] if not A[t]['blockers']]
    forced = [A[t] for t in include if t in A]  # added by the user from Top-rated now: always in the plan, still within limits
    floor = DIVERSIFIED_FLOOR[risk]
    funds_needed = math.ceil(floor / max(r['max_weight'], DIVERSIFIED_MAX[risk]) - 1e-9) if floor else 0
    for n in range(min(r['picks'], len(eligible)), len(eligible) + 1):
        picks = eligible[:n]
        # Make sure enough qualifying broad funds are in the plan to reach the diversified minimum.
        funds = [a for a in picks if SECTORS.get(a['ticker']) in DIVERSIFIED]
        picks += [a for a in eligible if SECTORS.get(a['ticker']) in DIVERSIFIED and a not in picks][:max(0, funds_needed - len(funds))]
        picks += [a for a in forced if a not in picks]
        weights, left = fill_weights(picks, r, risk)
        if picks and left <= 1e-6:
            return apply_floor(weights, r, risk, floor), False
    # Too few qualifying investments to respect every limit: add broad, diversified funds, then scale if still short.
    backups = [A[t] for t in analysis['ranked'] if SECTORS.get(t) in DIVERSIFIED and A[t] not in eligible]
    picks = eligible + backups + [a for a in forced if a not in eligible and a not in backups]
    if not picks:
        raise RuntimeError('Not enough market data to build a portfolio')
    weights, left = fill_weights(picks, r, risk)
    total = sum(weights.values())
    return apply_floor({t: w / total for t, w in weights.items()}, r, risk, floor), left > 1e-6


def plan_weights(analysis, risk, include=()):
    weights, relaxed = choose(analysis, risk, include)
    weights = {t: w for t, w in weights.items() if w >= 0.005 or t in include}
    total = sum(weights.values())
    return {t: w / total for t, w in weights.items()}, relaxed


def role(a):
    sector = SECTORS.get(a['ticker'])
    if a['kind'] == 'bond':
        return 'Stability: tends to move differently from stocks'
    if a['kind'] == 'commodity':
        return 'Diversifier: can hold up when stocks fall'
    if a['kind'] == 'etf':
        return 'Core: broad, diversified base' if sector in DIVERSIFIED else 'Sector boost: focused on one industry'
    if sector == 'technology':
        return 'Growth: higher potential, bigger swings'
    if sector in ('consumer staples', 'health care'):
        return 'Steady company: everyday products and services'
    return 'Individual company: targeted exposure'


def projection(initial, monthly, months, risk, weights, assets):
    mu = EXPECTED_RETURN[risk]
    # Diversification lowers swings versus the average holding; 0.75 is a rough, conservative adjustment.
    sigma = 0.75 * sum(w * (assets[t]['metrics']['vol'] or 0.2) for t, w in weights.items())
    spread = 1.2816 * sigma / math.sqrt(max(months / 12, 1 / 12))  # 10th/90th percentile of the average yearly return
    rates = {'pessimistic': max(-0.9, mu - spread), 'expected': mu, 'optimistic': mu + spread}
    values, contributed = dict.fromkeys(rates, float(initial)), float(initial)
    points = [{'month': 0, 'contributed': round(contributed, 2), **{k: round(v, 2) for k, v in values.items()}}]
    for month in range(1, months + 1):
        for k, rate in rates.items():
            values[k] = values[k] * (1 + rate) ** (1 / 12) + monthly
        contributed += monthly
        points.append({'month': month, 'contributed': round(contributed, 2), **{k: round(v, 2) for k, v in values.items()}})
    without_monthly = initial * (1 + mu) ** (months / 12)
    return points, rates, sigma, without_monthly


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def replay_plan(history, weights, initial, monthly, months):
    """Simulate the plan on real past closing prices: the one-time amount on day 1, then the monthly amount each month,
    each split by the plan's percentages, and the holdings valued every trading day up to the latest close."""
    tickers = list(weights)
    if 'SPY' not in history or any(t not in history for t in tickers):
        return None
    closes = {t: dict(zip(history[t]['dates'], history[t]['close'])) for t in tickers}
    dates = [d for d in history['SPY']['dates'] if all(d in closes[t] for t in tickers)]
    if len(dates) < 25:
        return None
    first, end = date.fromisoformat(dates[0]), date.fromisoformat(dates[-1])
    available = (end.year - first.year) * 12 + end.month - first.month - (1 if end.day < first.day else 0)
    replayed = max(1, min(months, available))
    start = dates[bisect.bisect_left(dates, add_months(end, -replayed).isoformat())]
    buys = {start: float(initial)}  # trading date -> money added that day
    for k in range(1, replayed + 1):
        i = min(bisect.bisect_left(dates, add_months(date.fromisoformat(start), k).isoformat()), len(dates) - 1)
        buys[dates[i]] = buys.get(dates[i], 0.) + monthly
    shares, put_in = dict.fromkeys(tickers, 0.), dict.fromkeys(tickers, 0.)
    contributed, points, months_rows, best, worst = 0., [], [], None, None
    for n, d in enumerate(dates[dates.index(start):]):
        added = buys.get(d, 0.)
        if added:
            for t, w in weights.items():
                shares[t] += added * w / closes[t][d]; put_in[t] += added * w
            contributed += added
        value = sum(shares[t] * closes[t][d] for t in tickers)
        gain = value - contributed
        if contributed > 0:
            best = max(best, (gain, d)) if best else (gain, d)
            worst = min(worst, (gain, d)) if worst else (gain, d)
        if d in buys:
            months_rows.append({'month': len(months_rows), 'date': d, 'added': round(added, 2), 'total_contributed': round(contributed, 2),
                                'value': round(value, 2), 'gain': round(gain, 2)})
        if n % 5 == 0 or d in buys or d == dates[-1]:
            points.append({'date': d, 'value': round(value, 2), 'contributed': round(contributed, 2)})
    final = sum(shares[t] * closes[t][dates[-1]] for t in tickers)
    initial_only = sum(initial * w * closes[t][dates[-1]] / closes[t][start] for t, w in weights.items()) if initial > 0 else None
    holdings = [{'ticker': t, 'shares': round(shares[t], 6), 'invested': round(put_in[t], 2), 'value': round(shares[t] * closes[t][dates[-1]], 2),
                 'gain': round(shares[t] * closes[t][dates[-1]] - put_in[t], 2),
                 'gain_pct': (shares[t] * closes[t][dates[-1]] / put_in[t] - 1) if put_in[t] else 0.} for t in tickers]
    return {
        'months_requested': months, 'months_replayed': replayed, 'capped': replayed < months, 'start_date': start, 'end_date': dates[-1],
        'total_contributed': round(contributed, 2), 'final_value': round(final, 2), 'gain': round(final - contributed, 2),
        'gain_pct': (final / contributed - 1) if contributed else 0.,
        'initial_only_value': round(initial_only, 2) if initial_only is not None else None,
        'best_point': {'date': best[1], 'gain': round(best[0], 2)} if best else None,
        'worst_point': {'date': worst[1], 'gain': round(worst[0], 2)} if worst else None,
        'months': months_rows, 'points': points, 'holdings': sorted(holdings, key=lambda h: -h['invested']),
        'note': ('A replay of your exact plan on real past closing prices: the one-time amount invested on the first day, then the monthly '
                 'amount added each month, both split by the recommended percentages. Important: these investments were chosen using '
                 'today’s data, partly because they have done well recently, so replaying them backward can look better than an investor '
                 'would really have done at the time. Fees, taxes and dividends are not included. Past results do not predict future results.'),
    }


def build_plan(initial, monthly, risk, months, market=None, universe=SIM_UNIVERSE, now=None, include=()):
    validate(initial, monthly, risk, months)
    include = list(dict.fromkeys(str(t).upper() for t in include))
    if len(include) > 5:
        raise ValueError('You can add up to 5 investments to a plan.')
    for t in include:
        if t not in universe:
            raise ValueError(f'{t} is not one of the stocks and ETFs InvestIQ analyzes.')
    archive = NewsArchive() if market is None else None
    market, now = live_market(market), now or datetime.now(timezone.utc)
    tf, tickers = timeframe_for(months), list(universe)
    history, fundamentals, headlines = market.history(tickers), market.fundamentals(tickers), market.headlines()
    news = latest_news(market, tickers, archive, now)
    analysis = analyze(history, fundamentals, news, headlines, risk, tf, universe, news_weight=NEWS_WEIGHT, now=now)
    weights, relaxed = plan_weights(analysis, risk, include)
    order = sorted(weights, key=lambda t: -weights[t])
    percents = round_to_total([weights[t] * 100 for t in order], 100, 0.1)
    # Dollars come from the displayed percentages, so 40% of $1,000 always shows as $400.
    initial_split = round_to_total([p / 100 * initial for p in percents], initial, 0.01)
    monthly_split = round_to_total([p / 100 * monthly for p in percents], monthly, 0.01)

    A, r = analysis['assets'], RISK[risk]
    tw = next(iter(A.values()))['weights']
    plan_analysis = {**analysis, 'targets': weights, 'cash_reserve': 0.}
    settings = {'risk': risk, 'timeframe': tf, 'months': months}
    assets = []
    for t, pct, one_time, per_month in zip(order, percents, initial_split, monthly_split):
        a = A[t]; m = a['metrics']; vol = m['vol'] or 0.2
        detail = explain('BUY', 'new', a, plan_analysis, settings, max(initial, monthly), max(one_time, per_month), m['price'], now)
        strengths = sorted((k for k in tw if tw[k] > 0 and (k != 'news' or a['components']['news'] > 0.55)), key=lambda k: -tw[k] * a['components'][k])[:2]
        sizing = 'its score divided by its volatility, so steadier investments get more' if risk != 'high' else 'its score'
        detail['why_amount'] = (f"{t} gets {pct:.1f}% of your money: {_usd(one_time)} of your one-time investment and {_usd(per_month)} of each monthly "
                                f"contribution. Its share starts from {sizing}. Then limits apply: at most {cap_for(t, r, risk):.0%} in {'this broad fund' if SECTORS.get(t) in DIVERSIFIED else 'one investment'}, "
                                f"{r['stock_share']:.0%} in individual company stocks and {r['sector_cap']:.0%} in one industry"
                                + (f", and at least {DIVERSIFIED_FLOOR[risk]:.0%} goes to broad, diversified funds for {r['label'].lower()} risk" if DIVERSIFIED_FLOOR[risk] else '')
                                + ". Money trimmed by a limit goes to the other picks, so the whole plan adds up to exactly 100%.")
        detail['price_note'] = price_note(now, m['date'], a['kind'])
        assets.append({'ticker': t, 'name': a['name'], 'kind': a['kind'], 'price': m['price'], 'price_date': m['date'],
                       'percent': pct, 'initial_amount': one_time, 'monthly_amount': per_month,
                       'risk_level': 'Low' if vol < 0.15 else 'Medium' if vol < 0.30 else 'High', 'volatility': vol, 'role': role(a),
                       'why': ('You added this from Top-rated now. ' if t in include else '')
                              + f"Scored {a['score']:.2f} (#{a['rank']} of {len(A)}); strongest on {' and '.join(COMPONENT_LABEL[k] for k in strengths)}.",
                       'downside': f"In a bad month (about 1 in 20) it could drop around {1.65 * vol * math.sqrt(21 / 252):.0%}, and bigger drops are possible."
                                   + (f" It doesn't pass every check for {r['label'].lower()} risk: {a['blockers'][0]}." if t in include and a['blockers'] else ''),
                       'added_by_user': t in include,
                       'analysis': detail})

    points, rates, sigma, without_monthly = projection(initial, monthly, months, risk, weights, A)
    end, contributed = points[-1], initial + monthly * months
    return {
        'inputs': {'initial': initial, 'monthly': monthly, 'risk': risk, 'risk_label': r['label'], 'months': months, 'include': include},
        'assets': assets,
        'totals': {'percent': round(sum(percents), 1), 'initial': round(sum(initial_split), 2), 'monthly': round(sum(monthly_split), 2)},
        'summary': {'total_contributed': round(contributed, 2),
                    **{f'{k}_end': end[k] for k in rates}, **{f'{k}_gain': round(end[k] - contributed, 2) for k in rates},
                    'without_monthly_end': round(without_monthly, 2), 'monthly_effect': round(end['expected'] - without_monthly, 2)},
        'projection': {'points': points, 'note': PROJECTION_NOTE,
                       'assumptions': {'expected_annual_return': rates['expected'], 'optimistic_annual_return': rates['optimistic'],
                                       'pessimistic_annual_return': rates['pessimistic'], 'portfolio_volatility': sigma}},
        'replay': replay_plan(history, weights, initial, monthly, months),
        'market': analysis['regime']['text'], 'relaxed_limits': relaxed,
        'price_note': price_note(now, history['SPY']['dates'][-1] if 'SPY' in history else 'the last trading day'),
        'generated_at': now.isoformat(), 'disclaimer': DISCLAIMER,
    }


def leaderboard(risk, months, market=None, universe=SIM_UNIVERSE, now=None):
    """Every stock and ETF ranked by the AI's score for this risk level and timeframe, with changes since the previous close.
    'Top-rated' means highest-scoring by InvestIQ's rules, not a prediction of which will rise."""
    if risk not in RISK:
        raise ValueError('Choose Low, Medium or High risk.')
    if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 120:
        raise ValueError('Choose an investment period between 1 and 120 months.')
    archive = NewsArchive() if market is None else None
    market, now = live_market(market), now or datetime.now(timezone.utc)
    tf, tickers = timeframe_for(months), list(universe)
    history, fundamentals, headlines = market.history(tickers), market.fundamentals(tickers), market.headlines()
    news = latest_news(market, tickers, archive, now)
    price_only = analyze(history, fundamentals, news, headlines, risk, tf, universe)  # the usual score, where news barely counts
    current = analyze(history, fundamentals, news, headlines, risk, tf, universe, news_weight=NEWS_WEIGHT, now=now)
    # Re-score with only what was known at the previous close, so "since yesterday" is real from the first visit.
    previous, compared_to = {}, None
    dates = history.get('SPY', {}).get('dates', [])
    if len(dates) >= 2:
        compared_to = dates[-2]
        past = HistoricalMarket(market)
        y, m_, d = (int(x) for x in compared_to.split('-'))
        past.as_of = datetime(y, m_, d, 16, 0, tzinfo=NY).astimezone(timezone.utc)
        try:
            before = analyze(past.history(tickers), fundamentals, {t: past._known(news[t]) for t in tickers}, past.headlines(), risk, tf, universe,
                             news_weight=NEWS_WEIGHT, now=past.as_of)
            previous = {t: (x['rank'], x['score']) for t, x in before['assets'].items()}
        except RuntimeError:
            compared_to = None
    try:  # Buy signals: exactly what the plan builder would buy today for this risk level and period
        buy = plan_weights(current, risk)[0]
    except RuntimeError:
        buy = {}
    order = sorted(buy, key=lambda t: -buy[t])
    pct = dict(zip(order, round_to_total([buy[t] * 100 for t in order], 100, 0.1))) if order else {}
    rows = []
    for t in current['ranked']:
        x = current['assets'][t]; m = x['metrics']; vol = m['vol'] or 0.2
        weights = x['weights']
        strengths = sorted((k for k in weights if weights[k] > 0 and (k != 'news' or x['components']['news'] > 0.55)), key=lambda k: -weights[k] * x['components'][k])[:2]
        above50 = m['sma50'] is not None and m['price'] > m['sma50']
        above200 = m['sma200'] is not None and m['price'] > m['sma200']
        prev = previous.get(t)
        headline = x['news'][0] if x['news'] else None
        rows.append({'rank': x['rank'], 'ticker': t, 'name': x['name'], 'kind': x['kind'], 'sector': SECTORS.get(t),
                     'price': m['price'], 'price_date': m['date'], 'score': round(x['score'], 3),
                     'rank_change': prev[0] - x['rank'] if prev else None, 'score_change': round(x['score'] - prev[1], 3) if prev else None,
                     'w1': m['w1'], 'm1': m['m1'], 'm3': m['m3'],
                     'trend': 'Uptrend' if above50 and above200 else 'Mixed' if above200 or above50 else 'Downtrend',
                     'risk_level': 'Low' if vol < 0.15 else 'Medium' if vol < 0.30 else 'High',
                     'qualifies': not x['blockers'], 'reason': x['blockers'][0] if x['blockers'] else None,
                     'strengths': [COMPONENT_LABEL[k] for k in strengths],
                     'news_moved': price_only['assets'][t]['rank'] - x['rank'], 'news': x['news_summary'],
                     'signal': 'Buy' if t in pct else ('Watch' if not x['blockers'] else 'Avoid'), 'buy_percent': pct.get(t),
                     'headlines': [{k: i.get(k) for k in ('title', 'source', 'published_at', 'url', 'tone')} for i in x['news'][:3]],
                     'headline': {k: headline.get(k) for k in ('title', 'source', 'published_at', 'url')} if headline else None})
    return {'risk': risk, 'risk_label': RISK[risk]['label'], 'months': months, 'rows': rows, 'compared_to': compared_to,
            'buy_now': [{'ticker': t, 'name': current['assets'][t]['name'], 'percent': p, 'score': round(current['assets'][t]['score'], 3)} for t, p in pct.items()],
            'timeframe_label': TIMEFRAME[tf]['label'], 'news_memory_days': round(NEWS_MEMORY[tf]['half_life_hours'] / 24, 1),
            'updated_at': now.isoformat(), 'news_weight': NEWS_WEIGHT, 'news_refresh_minutes': math.ceil(len(universe) / LIVE_ROTATION), 'price_note': price_note(now, dates[-1] if dates else 'the last trading day'),
            'note': (f'Ranked by InvestIQ’s rule-based score for your risk level and timeframe. Latest news makes up {NEWS_WEIGHT:.0%} of it: '
                     f'headlines for every stock are re-checked about every {math.ceil(len(universe) / LIVE_ROTATION)} minutes and newer ones count more. Their tone is judged '
                     'by keyword matching, which can misread a headline. Short periods weigh the last day of news most; longer periods remember weeks of saved headlines. '
                     'Price momentum, trend, RSI, volatility and fundamentals make up the rest. Buy signals are what this simulator would buy today for your risk level '
                     'and time period; they are practice signals for virtual money, not financial advice. A high rank is not a prediction that a stock will rise, and no result is guaranteed.')}


def refresh_oldest_news(market, tickers=SIM_UNIVERSE, count=LIVE_ROTATION):
    """Force-refresh the Yahoo headlines that were checked longest ago."""
    def checked(t):
        try:
            return json.loads((market.dir / f'news-{t}.json').read_text())['epoch']
        except (OSError, ValueError, KeyError):
            return 0
    fresh = YahooMarket(market.dir); fresh.news_ttl = 0
    for t in sorted(tickers, key=checked)[:count]:
        fresh.news(t)


def board_events(old, new, now):
    """What changed between two rankings: brand-new headlines and rank moves."""
    before, events = {r['ticker']: r for r in old['rows']}, []
    for r in new['rows']:
        o = before.get(r['ticker'])
        if not o:
            continue
        seen = {h['url'] for h in o['headlines']}
        fresh = [h for h in r['headlines'] if h['url'] not in seen]
        moved = o['rank'] - r['rank']
        if fresh or moved:
            events.append({'at': now.isoformat(), 'ticker': r['ticker'], 'name': r['name'], 'moved': moved, 'rank': r['rank'],
                           'headline': fresh[0] if fresh else None})
    return sorted(events, key=lambda e: (e['headline'] is None, -abs(e['moved'])))


def _public(entry):
    return {**entry['board'], 'events': entry['events'][:8], 'version': entry['version'], 'live': True}


def watch(risk, months, market=None, universe=SIM_UNIVERSE, now=None):
    """Latest live ranking for this risk level and period. Viewing it keeps it on the every-minute update list for 10 minutes."""
    key = (risk, months)
    with _live_lock:
        entry = _live.get(key)
        if entry:
            entry['watched_until'] = time.time() + LIVE_WATCH_SECONDS
            return _public(entry)
    board = leaderboard(risk, months, market=market, universe=universe, now=now)
    with _live_lock:
        entry = _live.setdefault(key, {'events': [], 'version': 0, 'universe': universe})
        entry.update(board=board, watched_until=time.time() + LIVE_WATCH_SECONDS, version=entry['version'] + 1)
        return _public(entry)


def live_tick(market=None, now=None):
    """Run every minute: re-check the oldest headlines, then re-rank every list someone is watching. Returns how many were updated."""
    with _live_lock:
        for key in [k for k, e in _live.items() if e['watched_until'] <= time.time()]:
            del _live[key]
        keys = list(_live)
    if not keys:
        return 0
    if market is None:
        refresh_oldest_news(YahooMarket())
    for key in keys:
        entry = _live.get(key)
        if not entry:
            continue
        stamp = now or datetime.now(timezone.utc)
        board = leaderboard(*key, market=market, universe=entry['universe'], now=stamp)
        with _live_lock:
            entry['events'] = (board_events(entry['board'], board, stamp) + entry['events'])[:LIVE_EVENTS]
            entry.update(board=board, version=entry['version'] + 1)
    return len(keys)
