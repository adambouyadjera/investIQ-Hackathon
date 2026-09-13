import { useCallback, useEffect, useState } from 'react';
import { BarChart3, Bot, ChevronRight, Coins, Info, Wallet, type LucideIcon } from 'lucide-react';
import api from '../api/client';
import AssetLogo from './AssetLogo';
import ProfitChart from './PortfolioChart';
import TradeHistory from './TradeHistory';
import TradeExplanation from './TradeExplanation';
import { type Portfolio, type ConfiguredPortfolio, type PTrade, type Risk, usd, signedUsd, signedPct, shares, dateTime, tone, apiError } from './portfolioTypes';

type Tab = 'activity' | 'history' | 'settings';
const TABS: [Tab, string][] = [['activity', 'Current Activity'], ['history', 'History'], ['settings', 'Settings']];
const RISKS: { key: Risk; label: string; hint: string }[] = [
  { key: 'low', label: 'Low', hint: 'Mostly broad funds and bonds' },
  { key: 'medium', label: 'Medium', hint: 'Funds, stocks, a little crypto' },
  { key: 'high', label: 'High', hint: 'More stocks and crypto, bigger swings' },
];
const REPLAY_DAYS = 30;
const amountOk = (v: string) => v.trim() !== '' && Number(v) >= 100 && Number(v) <= 1000000;
const monthsOk = (v: string) => Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 120;

function RiskChoice({ value, onChange, labelledBy }: { value: Risk | ''; onChange: (r: Risk) => void; labelledBy: string }) {
  return <div className="rd-choice-grid" role="radiogroup" aria-labelledby={labelledBy}>
    {RISKS.map(r => <button key={r.key} type="button" role="radio" aria-checked={value === r.key} className={value === r.key ? 'selected' : ''} onClick={() => onChange(r.key)}>
      <strong>{r.label}</strong><span>{r.hint}</span>
    </button>)}
  </div>;
}

function Questions({ amount, setAmount, risk, setRisk, months, setMonths, prefix }: { amount: string; setAmount: (v: string) => void; risk: Risk | ''; setRisk: (r: Risk) => void; months: string; setMonths: (v: string) => void; prefix: string }) {
  return <ol className="rd-questions">
    <li>
      <label htmlFor={`${prefix}-amount`}>How much would you like to invest?</label>
      <div className="rd-input-affix"><span>$</span><input id={`${prefix}-amount`} type="number" min="100" max="1000000" step="100" inputMode="decimal" placeholder="10000" value={amount} onChange={e => setAmount(e.target.value)} aria-describedby={`${prefix}-amount-hint`}/></div>
      <small id={`${prefix}-amount-hint`}>$100 to $1,000,000</small>
    </li>
    <li>
      <span id={`${prefix}-risk`} className="rd-question-label">What level of risk are you willing to take?</span>
      <RiskChoice value={risk} onChange={setRisk} labelledBy={`${prefix}-risk`}/>
    </li>
    <li>
      <label htmlFor={`${prefix}-months`}>How long would you like to invest?</label>
      <div className="rd-input-affix"><input id={`${prefix}-months`} type="number" min="1" max="120" step="1" inputMode="numeric" placeholder="12" value={months} onChange={e => setMonths(e.target.value)} aria-describedby={`${prefix}-months-hint`}/><span>months</span></div>
      <small id={`${prefix}-months-hint`}>1 to 120 months</small>
    </li>
  </ol>;
}

function Setup({ onDone }: { onDone: (p: Portfolio) => void }) {
  const [amount, setAmount] = useState(''), [risk, setRisk] = useState<Risk | ''>(''), [months, setMonths] = useState('');
  const [replay, setReplay] = useState(true);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const ready = amountOk(amount) && risk !== '' && monthsOk(months);
  async function start() {
    setBusy(true); setError('');
    const body = { amount: Number(amount), risk, months: Number(months) };
    try {
      onDone((await (replay ? api.post<Portfolio>('/research/portfolio/backfill', { ...body, days: REPLAY_DAYS }) : api.post<Portfolio>('/research/portfolio/setup', body))).data);
    } catch (e) { setError(apiError(e, 'Investor AI could not start. Try again.')); }
    finally { setBusy(false); }
  }
  return <section className="rd-psetup" aria-labelledby="setup-heading">
    <h2 id="setup-heading">Set up Investor AI</h2>
    <p className="rd-psetup-sub">Answer 3 questions. The AI manages a practice portfolio on live prices and explains every trade.</p>
    <Questions prefix="setup" amount={amount} setAmount={setAmount} risk={risk} setRisk={setRisk} months={months} setMonths={setMonths}/>
    <label className="rd-replay-toggle">
      <input type="checkbox" checked={replay} onChange={e => setReplay(e.target.checked)}/>
      <span><strong>Include the past month</strong><small>Replay the last {REPLAY_DAYS} days on real prices so you see results right away.</small></span>
    </label>
    {error && <p className="rd-feed-error" role="alert">{error}</p>}
    <button className="rd-primary rd-start" disabled={!ready || busy} onClick={() => void start()}>{busy ? (replay ? 'Replaying the past month…' : 'Analyzing the market…') : 'Start Investor AI'}</button>
    {busy && replay && <p className="rd-news-note" role="status">Replaying the past month. This can take a few minutes.</p>}
  </section>;
}

function statusText(d: ConfiguredPortfolio) {
  const next = d.next_review ? ` · next review ${dateTime(d.next_review)}` : '';
  if (d.status === 'paused') return 'Paused — not trading';
  if (d.status === 'waiting') return 'Waiting for market data';
  if (d.status === 'holding') return `Holding ${d.holdings.length} investment${d.holdings.length === 1 ? '' : 's'} and watching prices${next}`;
  return `Holding cash — nothing passed its checks${next}`;
}

const STATUS_LABEL: Record<ConfiguredPortfolio['status'], string> = { holding: 'Actively Trading', cash: 'Watching · all cash', paused: 'Paused', waiting: 'Waiting for data' };

function Kpi({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: React.ReactNode }) {
  return <section className="rd-kpi" aria-label={label}>
    <span className="rd-kpi-icon" aria-hidden="true"><Icon size={20}/></span>
    <div><span className="rd-kpi-label">{label}</span>{children}</div>
  </section>;
}

function CurrentActivity({ data: d, busy, onControl, onWhy, onHistory }: { data: ConfiguredPortfolio; busy: boolean; onControl: (a: 'pause' | 'resume' | 'review') => void; onWhy: (t: PTrade) => void; onHistory: () => void }) {
  const last = d.trades.at(-1);
  const arrow = d.total_return > 0.004 ? '▲' : d.total_return < -0.004 ? '▼' : '';
  const statusTone = d.status === 'paused' ? 'off' : d.status === 'waiting' ? 'warn' : 'on';
  return <>
    {d.error && <p className="rd-feed-error" role="alert">{d.error}</p>}
    <div className="rd-kpis">
      <Kpi icon={Wallet} label="Portfolio Value">
        <strong className="rd-kpi-value">{usd(d.portfolio_value)}</strong>
        <span className={`rd-kpi-sub ${tone(d.total_return)}`}>{arrow} {signedPct(d.total_return_pct)} <em>vs. start</em></span>
      </Kpi>
      <Kpi icon={BarChart3} label="Total Profit">
        <strong className={`rd-kpi-value ${tone(d.total_return)}`}>{signedUsd(d.total_return)}</strong>
        <span className={`rd-kpi-sub ${tone(d.total_return)}`}>{arrow} {signedPct(d.total_return_pct)} <em>on {usd(d.deposits)}</em></span>
      </Kpi>
      <Kpi icon={Coins} label="Available Cash">
        <strong className="rd-kpi-value">{usd(d.cash)}</strong>
        <span className="rd-kpi-sub"><em>{usd(d.invested)} invested</em></span>
      </Kpi>
      <Kpi icon={Bot} label="AI Status">
        <strong className={`rd-kpi-status ${statusTone}`} title={statusText(d)}><i/>{STATUS_LABEL[d.status]}</strong>
        <span className="rd-kpi-sub"><em>{d.settings.risk_label} risk · {d.settings.months} month{d.settings.months === 1 ? '' : 's'} · checks every {d.review_minutes} min 24/7{d.replay ? ` · replayed from ${new Date(`${d.replay.start}T12:00:00`).toLocaleDateString([], { month: 'short', day: 'numeric' })}` : ''}{d.last_checked ? ` · last ${new Date(d.last_checked).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}</em></span>
        <span className={`rd-market ${d.market_open ? 'open' : ''}`}>{d.market_open ? 'US market open · stocks, ETFs & crypto trading' : `US market closed · crypto trading 24/7 · stocks resume ${dateTime(d.next_market_open)}`}</span>
        <div className="rd-kpi-actions">
          <button disabled={busy || !d.enabled} onClick={() => onControl('review')}>{busy ? 'Working…' : 'Review now'}</button>
          <button disabled={busy} onClick={() => onControl(d.enabled ? 'pause' : 'resume')}>{d.enabled ? 'Pause' : 'Resume'}</button>
        </div>
      </Kpi>
    </div>

    <div className="rd-act-grid">
      <ProfitChart data={d} onSelect={onWhy}/>
      <div className="rd-act-side">
        <section className="rd-pcard" aria-labelledby="holdings-heading">
          <h3 id="holdings-heading">Current Holdings</h3>
          {d.holdings.length ? <div className="rd-table-scroll"><table className="rd-hold-table">
            <thead><tr><th>Symbol</th><th>Position Value</th><th>Allocation</th><th>Gain/Loss</th></tr></thead>
            <tbody>{d.holdings.map(h => <tr key={h.ticker}>
              <td><div className="rd-sym"><AssetLogo ticker={h.ticker}/><div><strong>{h.ticker}</strong><small title={h.name}>{h.name}</small></div></div></td>
              <td>{usd(h.value)}<small>{shares(h.shares)} {h.kind === 'crypto' ? 'coins' : 'sh'} · now {usd(h.price)}</small></td>
              <td>{(h.value / d.portfolio_value * 100).toFixed(1)}%</td>
              <td className={tone(h.unrealized_pnl)}>{signedUsd(h.unrealized_pnl)}<small className={tone(h.unrealized_pnl)}>{signedPct(h.unrealized_pct)} vs avg {usd(h.avg_cost)}</small></td>
            </tr>)}</tbody>
          </table></div> : <p className="rd-trades-empty">No investments right now — all cash.</p>}
        </section>

        <section className="rd-pcard" aria-labelledby="action-heading">
          <div className="rd-action-head"><h3 id="action-heading">Latest AI Trade</h3>{last && <time dateTime={last.time}>{dateTime(last.time)}</time>}</div>
          {last ? <div className="rd-action-row">
            <AssetLogo ticker={last.ticker} size={46}/>
            <div>
              <strong>{last.action === 'BUY' ? 'Bought' : 'Sold'} {shares(last.shares)} {last.kind === 'crypto' ? last.name : `shares of ${last.ticker}`}</strong>
              <small>{usd(last.value)} at {usd(last.price)}</small>
              <button className="rd-why-pill" onClick={() => onWhy(last)}><Info size={15} aria-hidden="true"/> Why This Trade?</button>
            </div>
            <button className="rd-chevron" onClick={onHistory} aria-label="See full trading history"><ChevronRight size={20}/></button>
          </div> : <p className="rd-trades-empty">No trades yet.</p>}
          {d.strategy && <div className="rd-action-plan">
            <span>Current plan · {d.strategy.summary}</span>
            {d.strategy.targets.length > 0 && <div className="rd-ptargets">
              {d.strategy.targets.map(t => <span key={t.ticker} title={t.name}><strong>{t.ticker}</strong> {Math.round(t.weight * 100)}%</span>)}
              <span><strong>Cash</strong> {Math.round(d.strategy.cash_reserve * 100)}%</span>
            </div>}
          </div>}
        </section>
      </div>
    </div>
  </>;
}

type SettingsAction = 'apply' | 'reset' | 'replay';
const CONFIRM_LABEL: Record<SettingsAction, string> = { apply: 'Yes, apply', reset: 'Yes, start over', replay: 'Yes, replay the past month' };

function Settings({ data: d, onApplied }: { data: ConfiguredPortfolio; onApplied: (p: Portfolio) => void }) {
  const [amount, setAmount] = useState(String(d.deposits)), [risk, setRisk] = useState<Risk>(d.settings.risk), [months, setMonths] = useState(String(d.settings.months));
  const [pending, setPending] = useState<{ action: SettingsAction; message: string } | null>(null);
  const [busy, setBusy] = useState<SettingsAction | null>(null), [error, setError] = useState('');
  const valid = amountOk(amount) && monthsOk(months);
  const delta = valid ? Number(amount) - d.deposits : 0;
  const tooLow = valid && -delta > d.portfolio_value - 0.01;
  const changed = valid && (Math.abs(delta) > 0.004 || risk !== d.settings.risk || Number(months) !== d.settings.months);
  let cashEffect = 'Your cash stays the same.';
  if (delta > 0.004) cashEffect = `Adds ${usd(delta)} to your cash (${usd(d.cash)} → ${usd(d.cash + delta)}). The bot may then invest part of it, following its plan.`;
  if (delta < -0.004) cashEffect = -delta <= d.cash
    ? `Takes ${usd(-delta)} out of your cash (${usd(d.cash)} → ${usd(d.cash + delta)}). You’ll be asked to confirm.`
    : `Takes ${usd(-delta)} out of the portfolio. Cash covers ${usd(d.cash)}, so the bot sells about ${usd(-delta - d.cash)} of investments first. You’ll be asked to confirm.`;

  async function run(action: SettingsAction, confirm: boolean) {
    setBusy(action); setError('');
    const body = { amount: Number(amount), risk, months: Number(months), confirm };
    try {
      const response = action === 'replay'
        ? await api.post<Portfolio>('/research/portfolio/backfill', { ...body, days: REPLAY_DAYS })
        : await api.post<Portfolio>('/research/portfolio/settings', { ...body, reset: action === 'reset' });
      onApplied(response.data);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (detail?.code === 'confirmation_required') setPending({ action, message: detail.message });
      else setError(apiError(e, 'The settings could not be applied. Try again.'));
    } finally { setBusy(null); }
  }
  const clearPending = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPending(null); };

  return <section className="rd-psettings" aria-labelledby="settings-heading">
    <h3 id="settings-heading">Change input settings</h3>
    <Questions prefix="settings" amount={amount} setAmount={clearPending(setAmount)} risk={risk} setRisk={clearPending(setRisk)} months={months} setMonths={clearPending(setMonths)}/>
    <div className="rd-effect" aria-live="polite">
      <p><strong>Cash:</strong> {tooLow ? `Your portfolio is worth ${usd(d.portfolio_value)}, so the amount can’t go below ${usd(d.deposits - d.portfolio_value)}. Use Start over instead.` : cashEffect}</p>
      {(risk !== d.settings.risk || Number(months) !== d.settings.months) && <p><strong>Plan:</strong> the bot rebuilds its plan with the new settings right away and may buy or sell.</p>}
      <p className="rd-why-note">Profit and loss are measured against the amount you enter. Applying keeps your trading history; replaying the past month replaces it.</p>
    </div>
    {error && <p className="rd-feed-error" role="alert">{error}</p>}
    {pending ? <div className="rd-confirm" role="alertdialog" aria-labelledby="confirm-text">
      <p id="confirm-text">{pending.message}</p>
      <div className="rd-pcontrols">
        <button className={pending.action === 'apply' ? 'rd-primary' : 'rd-danger'} disabled={!!busy} onClick={() => void run(pending.action, true)}>{busy ? (busy === 'replay' ? 'Replaying the past month…' : 'Applying…') : CONFIRM_LABEL[pending.action]}</button>
        <button className="rd-secondary" disabled={!!busy} onClick={() => setPending(null)}>Cancel</button>
      </div>
    </div> : <div className="rd-pcontrols">
      <button className="rd-primary" disabled={!changed || tooLow || !!busy} onClick={() => void run('apply', false)}>{busy === 'apply' ? 'Applying…' : 'Apply settings'}</button>
      <button className="rd-danger-outline" disabled={!valid || !!busy} onClick={() => void run('reset', false)}>Start over with {valid ? usd(Number(amount)) : 'this amount'}</button>
      <button className="rd-danger-outline" disabled={!valid || !!busy} onClick={() => void run('replay', false)}>Replay past month with these settings</button>
    </div>}
  </section>;
}

export default function PortfolioBot() {
  const [data, setData] = useState<Portfolio | null>(null);
  const [tab, setTab] = useState<Tab>('activity');
  const [selected, setSelected] = useState<PTrade | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setData((await api.get<Portfolio>('/research/portfolio')).data); setError(''); }
    catch { setError('Investor AI could not be loaded. Check that the local service is running.'); }
  }, []);
  useEffect(() => { void load(); const id = setInterval(() => void load(), 30000); return () => clearInterval(id); }, [load]);
  const closeWhy = useCallback(() => setSelected(null), []);
  async function control(action: 'pause' | 'resume' | 'review') {
    setBusy(true); setError('');
    try { setData((await api.post<Portfolio>('/research/portfolio/control', { action })).data); }
    catch (e) { setError(apiError(e, 'That did not work. Try again.')); }
    finally { setBusy(false); }
  }
  const applied = (p: Portfolio) => { setData(p); setTab('activity'); };

  if (!data) return <div className="rd-pbot">{error
    ? <p className="rd-feed-error" role="alert">{error} <button onClick={() => void load()}>Retry</button></p>
    : <p className="rd-news-note" role="status">Loading Investor AI…</p>}</div>;
  if (!data.configured) return <div className="rd-pbot"><Setup onDone={applied}/></div>;

  return <div className="rd-pbot">
    <div className="rd-bot-tabs" role="tablist" aria-label="Investor AI">
      {TABS.map(([key, label]) => <button key={key} role="tab" id={`bot-tab-${key}`} aria-selected={tab === key} aria-controls="bot-panel" className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}
    </div>
    {error && <p className="rd-feed-error" role="alert">{error}</p>}
    <div id="bot-panel" role="tabpanel" aria-labelledby={`bot-tab-${tab}`} className="rd-pbot">
      {tab === 'activity' && <CurrentActivity data={data} busy={busy} onControl={a => void control(a)} onWhy={setSelected} onHistory={() => setTab('history')}/>}
      {tab === 'history' && <TradeHistory data={data} onWhy={setSelected}/>}
      {tab === 'settings' && <Settings key={data.deposits + data.settings.risk + data.settings.months} data={data} onApplied={applied}/>}
    </div>
    {selected && <TradeExplanation trade={selected} onClose={closeWhy}/>}
  </div>;
}
