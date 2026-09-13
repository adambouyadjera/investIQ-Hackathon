import { useCallback, useEffect, useRef, useState } from 'react';
import { ResponsiveContainer, Tooltip, PieChart, Pie, Cell } from 'recharts';
import { Check, PenLine, Plus, RefreshCw, Wallet, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../api/client';
import AssetLogo from './AssetLogo';
import { type Explanation, type Risk, usd, signedPct, dateTime, apiError, tone } from './portfolioTypes';

type Method = 'manual' | 'recommend';
type Step = 'method' | 'details' | 'plan' | 'results';
type SimAsset = {
  ticker: string; name: string; kind: string; price: number; price_date: string; percent: number; initial_amount: number; monthly_amount: number;
  risk_level: string; role: string; why: string; downside: string; analysis: Explanation; added_by_user?: boolean;
};
type LbRow = {
  rank: number; ticker: string; name: string; kind: string; price: number; score: number; rank_change: number | null; score_change: number | null;
  w1: number | null; m1: number | null; trend: string; risk_level: string; qualifies: boolean; reason: string | null; strengths: string[];
  headline: { title: string; source: string; published_at: string | null; url: string } | null;
  news_moved: number; news: { positive: number; negative: number; neutral: number; total: number; oldest_at: string | null; recent: number; latest_at: string | null; tone: number } | null;
  signal: 'Buy' | 'Watch' | 'Avoid'; buy_percent: number | null;
  headlines: { title: string; source: string; published_at: string | null; url: string; tone: string }[];
};
type LiveEvent = { at: string; ticker: string; name: string; moved: number; rank: number; headline: { title: string; url: string; tone: string; source: string } | null };
type Board = { buy_now: { ticker: string; name: string; percent: number; score: number }[]; news_memory_days: number; timeframe_label: string; events: LiveEvent[]; version: number; news_weight: number; news_refresh_minutes: number; risk: Risk; risk_label: string; months: number; rows: LbRow[]; compared_to: string | null; updated_at: string; note: string };
const MAX_ADDED = 5;
type Point = { month: number; contributed: number; pessimistic: number; expected: number; optimistic: number };
type SimPlan = {
  inputs: { initial: number; monthly: number; risk: Risk; risk_label: string; months: number; include: string[] };
  assets: SimAsset[]; totals: { percent: number; initial: number; monthly: number };
  summary: { total_contributed: number; expected_end: number; optimistic_end: number; pessimistic_end: number; expected_gain: number; optimistic_gain: number; pessimistic_gain: number; without_monthly_end: number; monthly_effect: number };
  projection: { points: Point[]; note: string; assumptions: { expected_annual_return: number; optimistic_annual_return: number; pessimistic_annual_return: number } };
  replay: {
    months_requested: number; months_replayed: number; capped: boolean; start_date: string; end_date: string;
    total_contributed: number; final_value: number; gain: number; gain_pct: number; initial_only_value: number | null;
    best_point: { date: string; gain: number } | null; worst_point: { date: string; gain: number } | null;
    months: { month: number; date: string; added: number; total_contributed: number; value: number; gain: number }[];
    points: { date: string; value: number; contributed: number }[];
    holdings: { ticker: string; shares: number; invested: number; value: number; gain: number; gain_pct: number }[];
    note: string;
  } | null;
  market: string; price_note: string; disclaimer: string; generated_at: string;
};

const BILLS = [['housing', 'Housing (rent or mortgage)'], ['utilities', 'Utilities'], ['transportation', 'Transportation'], ['insurance', 'Insurance'],
  ['debt', 'Debt payments'], ['food', 'Food'], ['subscriptions', 'Subscriptions'], ['other', 'Other expenses']] as const;
type BillKey = typeof BILLS[number][0];
const RISKS: { key: Risk; label: string; hint: string }[] = [
  { key: 'low', label: 'Low', hint: 'Mostly diversified funds and bonds' },
  { key: 'medium', label: 'Medium', hint: 'A mix of funds and steady companies' },
  { key: 'high', label: 'High', hint: 'More growth stocks, bigger swings' },
];
const COLORS = ['#53a986', '#6a90cb', '#dbad53', '#c77dba', '#e79486', '#7fc4c9', '#a3b86c', '#d98c4f', '#9aa3f0'];
const amount = (v: string) => { const n = Number(v); return v.trim() !== '' && Number.isFinite(n) && n >= 0 ? n : null; };
const day = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });

// Emergency buffer: half of what's left after bills. Investment is capped at 20% of income; never "invest everything left".
export function recommend(incomeMonthly: number, bills: number | null) {
  const cap = incomeMonthly * 0.2;
  if (bills === null) return { income: incomeMonthly, bills: null, remaining: null, buffer: null, cap, recommended: Math.floor(incomeMonthly * 0.1 / 5) * 5, capped: false };
  const remaining = incomeMonthly - bills;
  if (remaining <= 0) return { income: incomeMonthly, bills, remaining, buffer: 0, cap, recommended: 0, capped: false };
  const buffer = remaining * 0.5;
  const raw = Math.min(remaining - buffer, cap);
  return { income: incomeMonthly, bills, remaining, buffer, cap, recommended: Math.floor(raw / 5) * 5, capped: remaining - buffer > cap };
}

function RiskChoice({ value, onChange, id }: { value: Risk | ''; onChange: (r: Risk) => void; id: string }) {
  return <div className="rd-choice-grid" role="radiogroup" aria-labelledby={id}>
    {RISKS.map(r => <button key={r.key} type="button" role="radio" aria-checked={value === r.key} className={value === r.key ? 'selected' : ''} onClick={() => onChange(r.key)}>
      <strong>{r.label}</strong><span>{r.hint}</span>
    </button>)}
  </div>;
}

function MoneyInput({ id, label, hint, value, onChange, placeholder }: { id: string; label: string; hint?: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return <label className="rd-sim-field" htmlFor={id}>{label}{hint && <small>{hint}</small>}
    <span className="rd-input-affix"><span>$</span><input id={id} type="number" min="0" step="any" inputMode="decimal" value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)}/></span>
  </label>;
}

function MonthsInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <label className="rd-sim-field" htmlFor="sim-months">How many months do you plan to invest?<small>1 to 120 months</small>
    <span className="rd-input-affix"><input id="sim-months" type="number" min="1" max="120" step="1" inputMode="numeric" value={value} placeholder="12" onChange={e => onChange(e.target.value)}/><span>months</span></span>
  </label>;
}

function Analysis({ asset, onClose }: { asset: SimAsset; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; };
  }, [onClose]);
  const e = asset.analysis;
  const section = (title: string, body: React.ReactNode) => <section><h4>{title}</h4>{body}</section>;
  return <div className="rd-modal-backdrop" onClick={onClose}>
    <div className="rd-modal" role="dialog" aria-modal="true" aria-labelledby="analysis-title" onClick={ev => ev.stopPropagation()}>
      <header>
        <div className="rd-why-head"><AssetLogo ticker={asset.ticker} size={40}/><div>
          <h3 id="analysis-title">{asset.name} ({asset.ticker})</h3>
          <p><span className="rd-sim-chip">Simulation</span> {asset.percent.toFixed(1)}% · {usd(asset.price)} per share · {asset.risk_level} risk</p>
        </div></div>
        <button ref={closeRef} className="rd-modal-close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="rd-modal-body">
        {section('Why this percentage', <p>{e.why_amount}</p>)}
        {section('Why it was selected', <><p>{e.why_asset}</p><ul className="rd-why-alts">{e.alternatives.map(a => <li key={a.ticker}><strong>{a.ticker}</strong> {a.name} · score {a.score.toFixed(2)} · <em>{a.status}</em><span>{a.reason}</span></li>)}</ul></>)}
        {section('Market trends', <><p>{e.market}</p><p>{e.price_movement}</p></>)}
        {section('Company fundamentals', <p>{e.fundamentals}</p>)}
        {section('Technical indicators', <p>{e.indicators}</p>)}
        {section('Volatility', <p>{e.volatility}</p>)}
        {section('Recent news', <>{e.news.length > 0 && <ul className="rd-why-news">{e.news.map(n => <li key={n.url}><a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a><span>{n.source}{n.published_at ? ` · ${dateTime(n.published_at)}` : ''}</span></li>)}</ul>}<p className="rd-why-note">{e.news_note}</p></>)}
        {section('Risks and possible downside', <><ul>{e.risk_factors.map(r => <li key={r}>{r}</li>)}</ul><p>{e.downside}</p></>)}
        <p className="rd-why-note">{e.price_note}</p>
        <p className="rd-why-disclaimer">Educational insight, not financial advice. No result is guaranteed.</p>
      </div>
    </div>
  </div>;
}

function Ago({ iso }: { iso: string }) {
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(id); }, []);
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  return <>{s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)} min ago` : `${Math.floor(s / 3600)}h ago`}</>;
}

function RankMonthsInput({ months, onMonths }: { months: number; onMonths: (m: number) => void }) {
  const [text, setText] = useState(String(months));
  useEffect(() => { setText(String(months)); }, [months]);
  const n = Number(text), ok = text.trim() !== '' && Number.isInteger(n) && n >= 1 && n <= 120;
  useEffect(() => {  // wait until they stop typing, so "36" doesn't load "3" first
    if (!ok || n === months) return;
    const id = setTimeout(() => onMonths(n), 600);
    return () => clearTimeout(id);
  }, [n, ok, months, onMonths]);
  return <label className="rd-lb-months">How many months?
    <input type="number" min={1} max={120} step={1} inputMode="numeric" value={text} onChange={e => setText(e.target.value)} aria-invalid={!ok}/>
    {!ok && <small className="rd-negative">Enter 1–120</small>}
  </label>;
}

function Leaderboard({ risk, months, onRisk, onMonths, added, inPlan, onToggle, busy }: { risk: Risk; months: number; onRisk?: (r: Risk) => void; onMonths?: (m: number) => void; added: string[]; inPlan: Set<string>; onToggle: (t: string) => void; busy?: boolean }) {
  const [board, setBoard] = useState<Board | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'stock' | 'etf'>('all');
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const prev = useRef<{ key: string; ranks: Map<string, number> }>({ key: '', ranks: new Map() });
  const load = useCallback(async (manual = false) => {
    if (manual) setLoading(true);
    try {
      const data = (await api.get<Board>('/research/simulator/leaderboard', { params: { risk, months } })).data, key = `${risk}-${months}`;
      // Highlight rows whose rank changed since the last update (not when the user switches risk level).
      const moved = prev.current.key === key ? new Set(data.rows.filter(r => prev.current.ranks.has(r.ticker) && prev.current.ranks.get(r.ticker) !== r.rank).map(r => r.ticker)) : new Set<string>();
      prev.current = { key, ranks: new Map(data.rows.map(r => [r.ticker, r.rank])) };
      setBoard(data); setError('');
      if (moved.size) { setFlash(moved); setTimeout(() => setFlash(new Set()), 4000); }
    }
    catch (e) { setError(apiError(e, 'The Top-rated list is unavailable right now.')); }
    finally { setLoading(false); }
  }, [risk, months]);
  useEffect(() => { void load(); const id = setInterval(() => void load(), 15000); return () => clearInterval(id); }, [load]);
  const rows = (board?.rows ?? []).filter(r => filter === 'all' || (filter === 'stock' ? r.kind === 'stock' : r.kind !== 'stock'));
  const change = (v: number | null) => v == null ? '—' : <span className={tone(v)}>{signedPct(v)}</span>;
  return <section className="rd-pcard rd-lb" aria-labelledby="lb-title">
    <div className="rd-phistory-head">
      <div><h3 id="lb-title">Top-rated now</h3>
        <span className="rd-lb-sub">{board && <span className="rd-live"><span className="rd-live-dot" aria-hidden="true"/>Live · updated <Ago iso={board.updated_at}/></span>}{board ? (board.compared_to ? ` · arrows vs. ${day(board.compared_to)} close` : '') : 'Loading rankings…'}</span></div>
      <div className="rd-lb-tools">
        {onRisk && <div className="rd-segment" role="group" aria-label="Rank for risk level">{RISKS.map(r => <button key={r.key} className={risk === r.key ? 'selected' : ''} aria-pressed={risk === r.key} onClick={() => onRisk(r.key)}>{r.label}</button>)}</div>}
        {onMonths && <RankMonthsInput months={months} onMonths={onMonths}/>}
        <div className="rd-segment" role="group" aria-label="Show">{(['all', 'stock', 'etf'] as const).map(f => <button key={f} className={filter === f ? 'selected' : ''} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f === 'all' ? 'All' : f === 'stock' ? 'Stocks' : 'ETFs'}</button>)}</div>
        <button className="rd-secondary rd-lb-refresh" onClick={() => void load(true)} disabled={loading} aria-label="Refresh rankings" title="Refresh rankings"><RefreshCw size={14}/></button>
      </div>
    </div>
    {error && <p className="rd-feed-error" role="alert">{error}</p>}
    {board && <div className="rd-lb-layout">
      <aside className="rd-lb-left" aria-labelledby="buy-title">
        <div className="rd-buynow">
          <div className="rd-buynow-head"><strong id="buy-title">Buy signals right now</strong>
            <span>{board.risk_label} risk · {months} month{months === 1 ? '' : 's'}</span></div>
          {board.buy_now.length > 0 ? <>
            <ul className="rd-buynow-list">{board.buy_now.map((b, i) => <li key={b.ticker} className="rd-buynow-item">
              <span className="rd-alloc-dot" style={{ background: COLORS[i % COLORS.length] }} aria-hidden="true"/>
              <AssetLogo ticker={b.ticker} size={24}/><div><strong>{b.ticker}</strong><small>{b.name}</small></div>
              <span className="rd-buynow-pct">{b.percent.toFixed(1)}%</span></li>)}</ul>
            <h4 className="rd-buynow-pie-title">How to split your money</h4>
            <div className="rd-pie-wrap" role="img" aria-label={`Pie chart: ${board.buy_now.map(b => `${b.ticker} ${b.percent.toFixed(1)}%`).join(', ')}`}>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={board.buy_now} dataKey="percent" nameKey="ticker" innerRadius={55} outerRadius={95} paddingAngle={1} stroke="none" isAnimationActive={false}>
                    {board.buy_now.map((b, i) => <Cell key={b.ticker} fill={COLORS[i % COLORS.length]}/>)}
                  </Pie>
                  <Tooltip formatter={v => `${Number(v).toFixed(1)}%`} contentStyle={{ background: '#1d2319', border: '1px solid #33372d', borderRadius: 8, fontSize: 12 }} itemStyle={{ color: '#e8ecdf' }}/>
                </PieChart>
              </ResponsiveContainer>
              <div className="rd-pie-center" aria-hidden="true"><strong>{board.buy_now.length}</strong><span>picks · 100%</span></div>
            </div>
          </> : <p className="rd-news-note">Nothing passes every check for {board.risk_label.toLowerCase()} risk over {months} month{months === 1 ? '' : 's'} right now.</p>}
          <p className="rd-news-note">Based on today's prices and news. Picks can change anytime.</p>
        </div>
      </aside>
      <div className="rd-lb-right">
    {board.events.length > 0 && <div className="rd-lb-events" aria-live="polite"><strong>Just in</strong><ul>{board.events.slice(0, 4).map(e => <li key={`${e.at}-${e.ticker}`}>
      <AssetLogo ticker={e.ticker} size={18}/>
      <span>{e.headline
        ? <>New {e.headline.tone === 'neutral' ? '' : `${e.headline.tone === 'positive' ? 'good' : 'bad'} `}headline for <b>{e.ticker}</b>: <a href={e.headline.url} target="_blank" rel="noopener noreferrer">{e.headline.title}</a>{e.moved !== 0 && <> · {e.moved > 0 ? `up ${e.moved}` : `down ${-e.moved}`} to #{e.rank}</>}</>
        : <><b>{e.ticker}</b> {e.moved > 0 ? `rose ${e.moved}` : `fell ${-e.moved}`} to #{e.rank}</>}
        <small> · <Ago iso={e.at}/></small></span></li>)}</ul></div>}
    <div className="rd-table-scroll"><table className="rd-sim-table rd-lb-table">
      <thead><tr><th>Rank</th><th>Stock / ETF</th><th>Score</th><th>Price</th><th>Trend · risk</th><th><span className="rd-sr-only">Action</span></th></tr></thead>
      <tbody>{rows.map(r => {
        const isAdded = added.includes(r.ticker), inside = inPlan.has(r.ticker) && !isAdded;
        return <tr key={r.ticker} className={flash.has(r.ticker) ? 'rd-lb-flash' : undefined}>
          <td className="rd-lb-rank"><strong>#{r.rank}</strong><span className={`rd-signal ${r.signal.toLowerCase()}`}>{r.signal}{r.buy_percent != null ? ` ${r.buy_percent.toFixed(0)}%` : ''}</span>{r.rank_change != null && <small className={r.rank_change > 0 ? 'rd-positive' : r.rank_change < 0 ? 'rd-negative' : ''} title="Change since the previous close">{r.rank_change > 0 ? `▲ ${r.rank_change}` : r.rank_change < 0 ? `▼ ${-r.rank_change}` : '—'}</small>}</td>
          <td><div className="rd-sym"><AssetLogo ticker={r.ticker} size={26}/><div><strong>{r.name}</strong><small>{r.ticker} · strong on {r.strengths.join(' & ')}</small></div></div>
            {!r.qualifies && r.reason && <p className="rd-sim-why rd-sim-down">Doesn't fit {board.risk_label.toLowerCase()} risk: {r.reason}.</p>}
            {(r.news_moved !== 0 || (r.news && r.news.total > 0)) && <div className="rd-lb-newsline">
              {r.news_moved !== 0 && <span className={`rd-news-badge ${r.news_moved > 0 ? 'up' : 'down'}`}>📰 News moved it {r.news_moved > 0 ? 'up' : 'down'} {Math.abs(r.news_moved)} {Math.abs(r.news_moved) === 1 ? 'place' : 'places'}</span>}
              {r.news && r.news.total > 0 && <span className="rd-lb-newscount">{r.news.positive} good · {r.news.negative} bad of {r.news.total} headlines{r.news.oldest_at ? ` since ${day(r.news.oldest_at.slice(0, 10))}` : ''}{r.news.recent ? ` · ${r.news.recent} in the last 24h` : ''}</span>}
            </div>}
            {r.headlines.length > 0 && <details className="rd-lb-newsdetails"><summary>Latest headlines</summary><ul className="rd-lb-headlines">{r.headlines.slice(0, 3).map(h => <li key={h.url}>
              <span className={`rd-tone-dot ${h.tone}`} title={`Headline tone: ${h.tone}`} aria-label={`${h.tone} headline`}/>
              <span><a href={h.url} target="_blank" rel="noopener noreferrer">{h.title}</a> · {h.source}{h.published_at ? `, ${dateTime(h.published_at)}` : ''}</span></li>)}</ul></details>}</td>
          <td className="rd-lb-scorecell"><span className="rd-lb-score" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(1, r.score)) * 100}%` }}/></span><strong>{r.score.toFixed(2)}</strong>
            {r.score_change != null && Math.abs(r.score_change) >= 0.005 && <small className={tone(r.score_change)}>{r.score_change > 0 ? '+' : ''}{r.score_change.toFixed(2)}</small>}</td>
          <td className="rd-lb-change"><strong>{usd(r.price)}</strong><span>1W {change(r.w1)}</span><span>1M {change(r.m1)}</span></td>
          <td className="rd-lb-tags"><span className={`rd-trend ${r.trend.toLowerCase()}`}>{r.trend}</span><span className={`rd-risk-tag ${r.risk_level.toLowerCase()}`}>{r.risk_level} risk</span></td>
          <td>{inside ? <span className="rd-lb-in"><Check size={14} aria-hidden="true"/> In your plan</span>
            : <button className={isAdded ? 'rd-lb-added' : 'rd-why-btn'} disabled={busy || (!isAdded && added.length >= MAX_ADDED)} onClick={() => onToggle(r.ticker)} aria-label={isAdded ? `Remove ${r.ticker} from plan` : `Add ${r.ticker} to plan`}>
                {isAdded ? <><X size={13} aria-hidden="true"/> Remove</> : <><Plus size={13} aria-hidden="true"/> Add</>}</button>}</td>
        </tr>;
      })}</tbody>
    </table></div>
      </div>
    </div>}
    {board && <p className="rd-news-note">Ranked by price trends, company data and news. <Link to="/?view=info">How it works</Link>{added.length >= MAX_ADDED ? ` · You can add up to ${MAX_ADDED}.` : ''}</p>}
  </section>;
}

function Results({ plan, onEdit, onAnalysis, added, onToggle, busy }: { plan: SimPlan; onEdit: () => void; onAnalysis: (a: SimAsset) => void; added: string[]; onToggle: (t: string) => void; busy: boolean }) {
  const i = plan.inputs;
  return <div className="rd-simres">
    <div className="rd-sim-head">
      <div><p className="rd-eyebrow">Your plan</p><h2>{usd(i.initial)} once + {usd(i.monthly)}/month · {i.risk_label} risk · {i.months} month{i.months === 1 ? '' : 's'}</h2></div>
      <button className="rd-secondary" onClick={onEdit}><PenLine size={15} aria-hidden="true"/> Edit Inputs</button>
    </div>

    <section className="rd-pcard" aria-labelledby="alloc-title">
      <div className="rd-phistory-head"><h3 id="alloc-title">Your recommended stocks and ETFs</h3><span>Prices as of {plan.assets[0]?.price_date}</span></div>
      <div className="rd-alloc-bar" role="img" aria-label={plan.assets.map(x => `${x.ticker} ${x.percent}%`).join(', ')}>
        {plan.assets.map((x, n) => <i key={x.ticker} style={{ width: `${x.percent}%`, background: COLORS[n % COLORS.length] }}/>)}
      </div>
      <div className="rd-table-scroll"><table className="rd-sim-table">
        <thead><tr><th>Stock / ETF</th><th>Price</th><th>Allocation</th><th>Of one-time {usd(i.initial)}</th><th>Of monthly {usd(i.monthly)}</th><th>Risk</th><th>Role</th><th><span className="rd-sr-only">Details</span></th></tr></thead>
        <tbody>{plan.assets.map((x, n) => <tr key={x.ticker}>
          <td><div className="rd-sym"><span className="rd-alloc-dot" style={{ background: COLORS[n % COLORS.length] }}/><AssetLogo ticker={x.ticker} size={28}/><div><strong>{x.name}</strong><small>{x.ticker}{x.added_by_user ? ' · added by you' : ''}</small></div></div>
            <p className="rd-sim-why">{x.why}</p><p className="rd-sim-why rd-sim-down">{x.downside}</p></td>
          <td>{usd(x.price)}</td>
          <td><strong>{x.percent.toFixed(1)}%</strong></td>
          <td>{usd(x.initial_amount)}</td>
          <td>{usd(x.monthly_amount)}</td>
          <td><span className={`rd-risk-tag ${x.risk_level.toLowerCase()}`}>{x.risk_level}</span></td>
          <td className="rd-sim-role">{x.role}</td>
          <td><button className="rd-why-btn" onClick={() => onAnalysis(x)}>View Detailed Analysis</button></td>
        </tr>)}</tbody>
        <tfoot><tr><td>Total</td><td/><td><strong>{plan.totals.percent.toFixed(1)}%</strong></td><td><strong>{usd(plan.totals.initial)}</strong></td><td><strong>{usd(plan.totals.monthly)}</strong></td><td colSpan={3}/></tr></tfoot>
      </table></div>
    </section>

    <Leaderboard risk={i.risk} months={i.months} added={added} inPlan={new Set(plan.assets.map(x => x.ticker))} onToggle={onToggle} busy={busy}/>
    {busy && <p className="rd-news-note" role="status">Updating your recommendations…</p>}

    <p className="rd-news-note">{plan.price_note} Not financial advice.</p>
  </div>;
}

export default function Simulator() {
  const [step, setStep] = useState<Step>('method');
  const [method, setMethod] = useState<Method>('manual');
  const [initial, setInitial] = useState(''), [monthly, setMonthly] = useState(''), [risk, setRisk] = useState<Risk | ''>(''), [months, setMonths] = useState('');
  const [income, setIncome] = useState(''), [period, setPeriod] = useState<'monthly' | 'annual'>('monthly');
  const [billsMode, setBillsMode] = useState<'items' | 'total'>('items');
  const [bills, setBills] = useState<Record<BillKey, string>>({ housing: '', utilities: '', transportation: '', insurance: '', debt: '', food: '', subscriptions: '', other: '' });
  const [billsTotal, setBillsTotal] = useState('');
  const [plan, setPlan] = useState<SimPlan | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [detail, setDetail] = useState<SimAsset | null>(null);
  const [added, setAdded] = useState<string[]>([]), [boardRisk, setBoardRisk] = useState<Risk>('medium'), [boardMonths, setBoardMonths] = useState(12);
  const closeDetail = useCallback(() => setDetail(null), []);

  const incomeValue = amount(income);
  const incomeMonthly = incomeValue === null ? null : period === 'annual' ? incomeValue / 12 : incomeValue;
  const itemized = BILLS.map(([k]) => amount(bills[k])).filter((v): v is number => v !== null);
  const billsValue = billsMode === 'total' ? amount(billsTotal) : itemized.length ? itemized.reduce((x, y) => x + y, 0) : null;
  const rec = incomeMonthly !== null && incomeMonthly > 0 ? recommend(incomeMonthly, billsValue) : null;

  const initialN = amount(initial) ?? 0, monthlyN = amount(monthly) ?? 0, monthsN = Number(months);
  const amountsOk = (initial === '' || amount(initial) !== null) && (monthly === '' || amount(monthly) !== null) && initialN <= 1000000 && monthlyN <= 100000 && initialN + monthlyN > 0;
  const planOk = amountsOk && risk !== '' && Number.isInteger(monthsN) && monthsN >= 1 && monthsN <= 120;

  async function run(include: string[] = added, scroll = true) {
    setBusy(true); setError('');
    try {
      setPlan((await api.post<SimPlan>('/research/simulator/plan', { initial: initialN, monthly: monthlyN, risk, months: monthsN, include })).data);
      setStep('results'); if (scroll) window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) { setError(apiError(e, 'Your recommendations could not load. Try again.')); }
    finally { setBusy(false); }
  }
  const choose = (m: Method) => { setMethod(m); setStep('details'); };
  const toggleAdded = (ticker: string, rerun: boolean) => {
    const next = added.includes(ticker) ? added.filter(t => t !== ticker) : added.length < MAX_ADDED ? [...added, ticker] : added;
    setAdded(next);
    if (rerun) void run(next, false);
  };
  const planFields = <>
    <MoneyInput id="sim-initial" label="One-time investment" hint="Money you invest at the start (optional)" value={initial} onChange={setInitial} placeholder="1000"/>
    <MoneyInput id="sim-monthly" label="Monthly investment" hint="Added every month (optional)" value={monthly} onChange={setMonthly} placeholder="100"/>
    <div className="rd-sim-field"><span id="sim-risk">What level of risk are you comfortable with?</span><RiskChoice id="sim-risk" value={risk} onChange={setRisk}/></div>
    <MonthsInput value={months} onChange={setMonths}/>
  </>;
  const runButton = <>
    {added.length > 0 && <div className="rd-lb-chips"><span>You added:</span>{added.map(t => <button key={t} onClick={() => toggleAdded(t, false)} aria-label={`Remove ${t}`}>{t} <X size={12} aria-hidden="true"/></button>)}</div>}
    {error && <p className="rd-feed-error" role="alert">{error}</p>}
    <button className="rd-primary rd-start" disabled={!planOk || busy} onClick={() => void run()}>{busy ? 'Building your portfolio…' : 'Get My Recommendations'}</button>
    {!amountsOk && (initial !== '' || monthly !== '') && <p className="rd-news-note">Enter a one-time or monthly amount (up to $1,000,000 one-time and $100,000 monthly).</p>}
  </>;

  return <section className="rd-detail rd-sim" aria-label="Stock recommendations">

    {step === 'method' && added.length > 0 && <p className="rd-news-note">{added.join(', ')} will be included when you run your plan.</p>}
    {step === 'method' && <h2 className="rd-section-title">Get your personalized plan</h2>}
    {step === 'method' && <div className="rd-sim-methods">
      <button onClick={() => choose('manual')}><PenLine size={22} aria-hidden="true"/><strong>I know my amount</strong><span>Enter what you'll invest now and each month.</span></button>
      <button onClick={() => choose('recommend')}><Wallet size={22} aria-hidden="true"/><strong>Suggest an amount for me</strong><span>We'll use your income and bills.</span></button>
    </div>}
    {step === 'method' && <Leaderboard risk={boardRisk} months={boardMonths} onRisk={setBoardRisk} onMonths={setBoardMonths} added={added} inPlan={new Set()} onToggle={t => toggleAdded(t, false)}/>}

    {step !== 'method' && step !== 'results' && <button className="rd-link-btn rd-sim-back" onClick={() => setStep(step === 'plan' ? 'details' : 'method')}>← Back</button>}

    {step === 'details' && method === 'manual' && <div className="rd-psettings">
      <h3>Enter your investment</h3>
      {planFields}
      {runButton}
    </div>}

    {step === 'details' && method === 'recommend' && <div className="rd-psettings">
      <h3>Your finances</h3>
      <div className="rd-sim-income">
        <MoneyInput id="sim-income" label="Income after taxes" value={income} onChange={setIncome} placeholder={period === 'monthly' ? '4000' : '48000'}/>
        <div className="rd-segment" role="group" aria-label="Income period">
          <button className={period === 'monthly' ? 'selected' : ''} aria-pressed={period === 'monthly'} onClick={() => setPeriod('monthly')}>Monthly</button>
          <button className={period === 'annual' ? 'selected' : ''} aria-pressed={period === 'annual'} onClick={() => setPeriod('annual')}>Annual</button>
        </div>
      </div>
      <details className="rd-sim-bills">
        <summary>Monthly bills and expenses <span className="rd-optional">Optional</span></summary>
        <div className="rd-segment" role="group" aria-label="How to enter bills">
          <button className={billsMode === 'items' ? 'selected' : ''} aria-pressed={billsMode === 'items'} onClick={() => setBillsMode('items')}>Enter each bill</button>
          <button className={billsMode === 'total' ? 'selected' : ''} aria-pressed={billsMode === 'total'} onClick={() => setBillsMode('total')}>One total</button>
        </div>
        {billsMode === 'items'
          ? <div className="rd-sim-bill-grid">{BILLS.map(([k, label]) => <MoneyInput key={k} id={`bill-${k}`} label={label} value={bills[k]} onChange={v => setBills(b => ({ ...b, [k]: v }))} placeholder="0"/>)}</div>
          : <MoneyInput id="bill-total" label="Total monthly bills and expenses" value={billsTotal} onChange={setBillsTotal} placeholder="2500"/>}
      </details>
      {rec && <div className="rd-breakdown" aria-live="polite">
        <h4>How we calculated it</h4>
        <dl>
          <div><dt>Monthly income</dt><dd>{usd(rec.income)}</dd></div>
          <div><dt>Total monthly bills</dt><dd>{rec.bills === null ? 'Not entered' : `− ${usd(rec.bills)}`}</dd></div>
          {rec.remaining !== null && <div><dt>Money left each month</dt><dd className={tone(rec.remaining)}>{usd(rec.remaining)}</dd></div>}
          {rec.buffer !== null && rec.remaining !== null && rec.remaining > 0 && <div><dt>Emergency savings / cash buffer <small>half of what's left</small></dt><dd>− {usd(rec.buffer)}</dd></div>}
          <div className="total"><dt>Recommended monthly investment {rec.capped && <small>capped at 20% of income</small>}{rec.bills === null && <small>10% of income, since bills weren't entered</small>}</dt><dd>{usd(rec.recommended)}</dd></div>
        </dl>
        {rec.remaining !== null && rec.remaining <= 0 && <p className="rd-feed-error">Your bills are equal to or more than your income, so we don't recommend investing monthly right now.</p>}
        <div className="rd-pcontrols">
          <button className="rd-primary" onClick={() => { setMonthly(String(rec.recommended)); setStep('plan'); }}>Use {usd(rec.recommended)} a month</button>
          <button className="rd-secondary" onClick={() => { setMonthly(monthly || String(rec.recommended)); setStep('plan'); }}>Choose my own amount</button>
        </div>
      </div>}
    </div>}

    {step === 'plan' && <div className="rd-psettings">
      <h3>Confirm your plan</h3>
      {rec && <p className="rd-news-note">Recommended monthly investment: {usd(rec.recommended)}. You can change it below.</p>}
      {planFields}
      {runButton}
    </div>}

    {step === 'results' && plan && <Results plan={plan} onEdit={() => setStep(method === 'recommend' ? 'plan' : 'details')} onAnalysis={setDetail} added={added} onToggle={t => toggleAdded(t, true)} busy={busy}/>}
    {detail && <Analysis asset={detail} onClose={closeDetail}/>}
  </section>;
}
