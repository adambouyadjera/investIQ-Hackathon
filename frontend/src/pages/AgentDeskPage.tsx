import { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import {
  Bot, ShieldCheck, TriangleAlert, Newspaper, FlaskConical, ChevronDown, ChevronRight,
  ArrowUpRight, ArrowDownRight, Minus, Info, Lock,
} from 'lucide-react';
import { Layout } from '../components/layout/Layout';
import { Card, StatCard } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import {
  backtest, getAgentConfig, getRegimeHistory, scan, walkForward,
  type AgentConfig, type BacktestReport, type Evidence, type Proposal,
  type RegimeHistory, type ScanResult, type WalkForwardReport,
} from '../api/agent';

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const pct = (n: number) => `${(n * 100).toFixed(2)}%`;
const signed = (n: number) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`;
const num = (n: number, d = 2) => n.toFixed(d);

const REGIME_COLOR: Record<string, 'green' | 'yellow' | 'red' | 'gray'> = {
  calm: 'green', volatile: 'yellow', bear: 'red', unknown: 'gray',
};

type Tab = 'scan' | 'backtest' | 'walkforward';

/* ── The explainability visual ─────────────────────────────────────────────
   A diverging bar per piece of evidence. The bars are drawn to a shared
   scale and are labelled with the exact contribution, so the reader can add
   them up and land on the score. That reconstruction is the whole point --
   a score you cannot re-derive by hand is not an explanation.            */
function EvidenceWaterfall({ evidence, rawScore, conviction, score }: {
  evidence: Evidence[]; rawScore: number; conviction: number; score: number;
}) {
  const max = Math.max(0.001, ...evidence.map((e) => Math.abs(e.contribution)));
  return (
    <div className="space-y-2">
      {evidence.map((e) => {
        const width = (Math.abs(e.contribution) / max) * 50;
        const positive = e.contribution >= 0;
        return (
          <div key={e.name} className="flex items-center gap-3 text-xs" title={e.note}>
            <span className="w-20 shrink-0 text-gray-400 capitalize">{e.name}</span>
            <span className="w-16 shrink-0 text-right text-gray-500 tabular-nums">
              {e.raw >= 0 ? '+' : ''}{num(e.raw, 3)}
            </span>
            <span className="w-10 shrink-0 text-right text-gray-600 tabular-nums">
              ×{num(e.weight, 2)}
            </span>
            <div className="flex-1 h-4 relative bg-gray-900/60 rounded">
              <div className="absolute inset-y-0 left-1/2 w-px bg-gray-700" />
              <div
                className={`absolute inset-y-0.5 rounded ${positive ? 'bg-emerald-500/70' : 'bg-red-500/70'}`}
                style={
                  positive
                    ? { left: '50%', width: `${width}%` }
                    : { right: '50%', width: `${width}%` }
                }
              />
            </div>
            <span
              className={`w-16 shrink-0 text-right tabular-nums font-medium ${
                positive ? 'text-emerald-400' : 'text-red-400'
              }`}
            >
              {e.contribution >= 0 ? '+' : ''}{num(e.contribution, 4)}
            </span>
          </div>
        );
      })}

      <div className="pt-2 mt-1 border-t border-gray-700 space-y-1 text-xs">
        <div className="flex justify-between text-gray-300">
          <span>Sum of contributions</span>
          <span className="tabular-nums font-semibold">
            {rawScore >= 0 ? '+' : ''}{num(rawScore, 4)}
          </span>
        </div>
        <div className="flex justify-between text-gray-500">
          <span title="Damps conviction when realised volatility is unusually high. Never affects position size.">
            × volatility conviction
          </span>
          <span className="tabular-nums">{num(conviction, 4)}</span>
        </div>
        <div className="flex justify-between text-gray-100 font-semibold">
          <span>Score</span>
          <span className="tabular-nums">{score >= 0 ? '+' : ''}{num(score, 4)}</span>
        </div>
      </div>
    </div>
  );
}

function NewsPanel({ p }: { p: Proposal }) {
  if (!p.news) return null;
  const n = p.news;
  return (
    <div className="mt-3 pt-3 border-t border-gray-700">
      <div className="flex items-center gap-2 mb-2">
        <Newspaper className="w-3.5 h-3.5 text-gray-400" />
        <span className="text-xs font-medium text-gray-300">
          News sentiment {n.value >= 0 ? '+' : ''}{num(n.value, 3)}
        </span>
        <Badge color={n.source === 'synthetic' ? 'yellow' : 'gray'}>
          {n.source}
        </Badge>
        {n.thin_coverage && <Badge color="yellow">thin coverage — damped</Badge>}
        <span className="text-xs text-gray-500">
          {n.coverage} headline{n.coverage === 1 ? '' : 's'} / 10 days
        </span>
      </div>
      {n.drivers.length === 0 ? (
        <p className="text-xs text-gray-500">No headlines in the window.</p>
      ) : (
        <ul className="space-y-1.5">
          {n.drivers.map((d, i) => (
            <li key={i} className="text-xs">
              <div className="flex items-start gap-2">
                <span
                  className={`mt-0.5 tabular-nums shrink-0 ${
                    d.contribution >= 0 ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {d.contribution >= 0 ? '+' : ''}{num(d.contribution, 3)}
                </span>
                <div className="min-w-0">
                  <p className="text-gray-300">{d.text}</p>
                  <p className="text-gray-600">
                    matched: {d.matched_terms} · decay {num(d.decay, 2)} ·{' '}
                    {new Date(d.published_at).toLocaleString()}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProposalRow({ p, open, onToggle }: {
  p: Proposal; open: boolean; onToggle: () => void;
}) {
  const Icon = p.action === 'long' ? ArrowUpRight : p.action === 'short' ? ArrowDownRight : Minus;
  const tone =
    p.action === 'long' ? 'text-emerald-400'
      : p.action === 'short' ? 'text-red-400' : 'text-gray-500';

  return (
    <div className="border-b border-gray-800 last:border-0">
      <button
        onClick={onToggle}
        aria-expanded={open}
        className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-gray-800/60 transition-colors text-left"
      >
        {open ? <ChevronDown className="w-4 h-4 text-gray-500 shrink-0" />
              : <ChevronRight className="w-4 h-4 text-gray-500 shrink-0" />}
        <span className="w-16 font-medium text-gray-100">{p.symbol}</span>
        <Icon className={`w-4 h-4 shrink-0 ${tone}`} />
        <span className={`w-14 text-sm ${tone}`}>{p.action}</span>
        <span className="w-20 text-sm tabular-nums text-gray-200">
          {p.score >= 0 ? '+' : ''}{num(p.score, 3)}
        </span>
        <span className="flex-1 min-w-0 truncate text-xs text-gray-500">
          {p.intent
            ? `entry ${num(p.intent.entry)} · stop ${num(p.intent.stop)} · ${num(p.intent.risk_reward, 1)}R`
            : p.skip_reason}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 bg-gray-900/40">
          <EvidenceWaterfall
            evidence={p.evidence}
            rawScore={p.raw_score}
            conviction={p.conviction}
            score={p.score}
          />
          {p.intent && (
            <div className="mt-3 pt-3 border-t border-gray-700 grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
              {[
                ['Entry', num(p.intent.entry)],
                ['Stop', num(p.intent.stop)],
                ['Target 1', num(p.intent.target_1)],
                ['Target 2', num(p.intent.target_2)],
                ['Reward', `${num(p.intent.risk_reward, 2)}R after costs`],
              ].map(([k, v]) => (
                <div key={k}>
                  <p className="text-gray-500">{k}</p>
                  <p className="text-gray-200 tabular-nums">{v}</p>
                </div>
              ))}
              <div className="col-span-2 sm:col-span-5">
                <p className="text-gray-500">Invalidation</p>
                <p className="text-gray-300">{p.intent.invalidation}</p>
              </div>
              <div className="col-span-2 sm:col-span-5 flex items-start gap-2 text-gray-500">
                <Lock className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>
                  No position size appears here. The agent proposes; sizing is the
                  risk engine's decision, computed from the stop distance and
                  account equity.
                </span>
              </div>
            </div>
          )}
          <NewsPanel p={p} />
        </div>
      )}
    </div>
  );
}

function EquityChart({ report }: { report: BacktestReport }) {
  const data = useMemo(
    () => report.equity_curve.filter((_, i) => i % 3 === 0),
    [report.equity_curve],
  );
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 5, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} minTickGap={60} />
        <YAxis
          tick={{ fill: '#9ca3af', fontSize: 11 }}
          tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
          domain={['auto', 'auto']}
        />
        <Tooltip
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
          labelStyle={{ color: '#e5e7eb' }}
          formatter={(val: any, name: any) => [money(val), name]}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="strategy" name="Agent (paper)" stroke="#818cf8"
              dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="benchmark" name="Buy & hold" stroke="#34d399"
              dot={false} strokeWidth={2} strokeDasharray="4 3" />
      </LineChart>
    </ResponsiveContainer>
  );
}

function VerdictBanner({ report }: { report: BacktestReport }) {
  const b = report.benchmark;
  const s = report.significance;
  const beat = b.beat_benchmark;
  return (
    <div
      className={`rounded-xl border p-4 ${
        beat ? 'bg-emerald-900/20 border-emerald-800' : 'bg-amber-900/20 border-amber-800'
      }`}
    >
      <div className="flex items-start gap-3">
        <TriangleAlert className={`w-5 h-5 mt-0.5 shrink-0 ${beat ? 'text-emerald-400' : 'text-amber-400'}`} />
        <div className="text-sm">
          <p className="font-semibold text-gray-100">
            {beat
              ? 'Beat buy-and-hold on CAGR over this window.'
              : 'Did not beat buy-and-hold on CAGR over this window.'}
          </p>
          <p className="text-gray-300 mt-1">
            Strategy {signed(b.strategy_total_return)} vs benchmark{' '}
            {signed(b.benchmark_total_return)} · max drawdown{' '}
            {pct(b.strategy.max_drawdown)} vs {pct(b.benchmark.max_drawdown)} · beta{' '}
            {num(b.beta, 2)}.
          </p>
          <p className="text-gray-400 mt-1">
            Significance after adjusting for {s.n_trials} declared trial
            {s.n_trials === 1 ? '' : 's'}: <span className="font-medium">{s.verdict}</span>
            {s.deflated_sharpe !== null && ` (deflated Sharpe ${num(s.deflated_sharpe, 3)})`}.
          </p>
        </div>
      </div>
    </div>
  );
}

function ReportBody({ report }: { report: BacktestReport }) {
  const b = report.benchmark;
  const vetoes = Object.entries(report.risk.vetoes);
  return (
    <div className="space-y-4">
      <VerdictBanner report={report} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Final equity" value={money(report.broker.final_equity)}
          sub={`from ${money(report.broker.initial_cash)}`}
          color={report.broker.net_profit >= 0 ? 'green' : 'red'} />
        <StatCard label="Excess CAGR vs benchmark" value={signed(b.excess_cagr)}
          sub={`alpha ${signed(b.alpha_annualized)} · beta ${num(b.beta, 2)}`}
          color={b.excess_cagr >= 0 ? 'green' : 'red'} />
        <StatCard label="Max drawdown" value={pct(b.strategy.max_drawdown)}
          sub={`benchmark ${pct(b.benchmark.max_drawdown)}`}
          color={b.drawdown_advantage >= 0 ? 'green' : 'red'} />
        <StatCard label="Costs paid" value={money(report.broker.total_costs)}
          sub={`${pct(report.broker.cost_drag_pct)} of starting capital`} color="yellow" />
      </div>

      <Card title="Equity curve against buy-and-hold"
            subtitle={`${report.window.start} to ${report.window.end} · ${report.window.years} years · both pay the same entry costs`}>
        <EquityChart report={report} />
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Trading record" subtitle="Every fill crossed the spread and paid commission">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            {[
              ['Closed trades', String(report.broker.closed_trades)],
              ['Win rate', pct(report.broker.win_rate)],
              ['Profit factor', report.broker.profit_factor === null ? '—' : num(report.broker.profit_factor, 3)],
              ['Average win', money(report.broker.avg_win)],
              ['Average loss', money(report.broker.avg_loss)],
              ['Borrow paid', money(report.broker.borrow_paid)],
              ['Information ratio', b.information_ratio === null ? '—' : num(b.information_ratio, 3)],
              ['Tracking error', pct(b.tracking_error)],
              ['Up capture', b.up_capture === null ? '—' : num(b.up_capture, 2)],
              ['Down capture', b.down_capture === null ? '—' : num(b.down_capture, 2)],
            ].map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-gray-400">{k}</dt>
                <dd className="text-gray-100 text-right tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card title="What the risk engine refused"
              subtitle={`${report.risk.veto_total} proposals blocked before reaching the book`}>
          {vetoes.length === 0 ? (
            <p className="text-sm text-gray-500">Nothing was refused in this window.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {vetoes.map(([code, n]) => (
                <li key={code} className="flex justify-between gap-3">
                  <span className="text-gray-300 font-mono text-xs">{code}</span>
                  <span className="text-gray-400 tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          )}
          {report.risk.breaker_events.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <p className="text-xs font-medium text-amber-300 mb-1.5">
                Circuit breakers fired {report.risk.breaker_events.length} time
                {report.risk.breaker_events.length === 1 ? '' : 's'}
              </p>
              <ul className="space-y-1 text-xs text-gray-400">
                {report.risk.breaker_events.slice(0, 5).map((e, i) => (
                  <li key={i}>
                    <span className="text-gray-300">{e.date}</span> — {e.action}: {e.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-3 text-xs text-gray-600 font-mono">
            policy {report.risk.policy_hash} · weights {report.risk.weights_hash}
          </p>
        </Card>
      </div>

      <Card title="Read this before believing any number above"
            subtitle="Stated by the harness, not added afterwards">
        <ul className="space-y-2 text-sm text-gray-400">
          {report.caveats.map((c, i) => (
            <li key={i} className="flex gap-2">
              <Info className="w-4 h-4 mt-0.5 shrink-0 text-gray-600" />
              <span>{c}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export default function AgentDeskPage() {
  const [tab, setTab] = useState<Tab>('scan');
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [regime, setRegime] = useState<RegimeHistory | null>(null);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [report, setReport] = useState<BacktestReport | null>(null);
  const [wf, setWf] = useState<WalkForwardReport | null>(null);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [start, setStart] = useState('2022-01-01');
  const [trials, setTrials] = useState(6);
  const [useNews, setUseNews] = useState(true);
  const [slippage, setSlippage] = useState(3);

  useEffect(() => {
    getAgentConfig().then(setConfig).catch(() => {});
    getRegimeHistory(180).then(setRegime).catch(() => {});
    run('scan');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run(which: Tab) {
    setLoading(true);
    setError('');
    try {
      const costs = { slippage_bps: slippage };
      if (which === 'scan') {
        setScanResult(await scan({ use_news: useNews, ...costs }));
      } else if (which === 'backtest') {
        setReport(await backtest({ start, n_trials: trials, use_news: useNews, ...costs }));
      } else {
        setWf(await walkForward({ split: start, n_trials: trials, use_news: useNews, ...costs }));
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(
        Array.isArray(detail)
          ? detail.map((d: any) => d.message ?? d.msg).join(' · ')
          : detail || 'Could not reach the agent desk.',
      );
    } finally {
      setLoading(false);
    }
  }

  const shown = scanResult?.proposals ?? [];

  return (
    <Layout>
      {/* Paper-only banner. Deliberately the first thing on the page. */}
      <div className="mb-4 rounded-xl border border-indigo-800 bg-indigo-900/30 px-4 py-3">
        <div className="flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-indigo-300 mt-0.5 shrink-0" />
          <div className="text-sm">
            <p className="font-semibold text-indigo-100">
              Paper trading only — this software cannot place a real order.
            </p>
            <p className="text-indigo-200/80 mt-0.5">
              There is no broker connection, no API credential and no live mode.
              Everything below is a simulation on historical prices, for learning
              how a strategy is evaluated. Not financial advice.
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-3">
          <Bot className="w-6 h-6 text-indigo-400" />
          <div>
            <h1 className="text-xl font-bold text-gray-100">Agent desk</h1>
            <p className="text-sm text-gray-400">
              Explainable signals, tested against a benchmark with real costs
            </p>
          </div>
        </div>
        {regime && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Market regime</span>
            <Badge color={REGIME_COLOR[regime.current] ?? 'gray'}>
              {regime.current} · {regime.current_stability} bars
            </Badge>
            {regime.current_stability < regime.min_stability_to_trade && (
              <Badge color="yellow">too unstable to trade</Badge>
            )}
          </div>
        )}
      </div>

      {/* Controls */}
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-gray-400">
            <span className="block mb-1">
              {tab === 'walkforward' ? 'Split date' : 'Start date'}
            </span>
            <input
              type="date" value={start} onChange={(e) => setStart(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-gray-100"
            />
          </label>
          <label className="text-xs text-gray-400">
            <span className="block mb-1" title="How many strategy variants you examined before choosing this one. Raising it raises the bar the result must clear.">
              Declared trials
            </span>
            <input
              type="number" min={1} max={1000} value={trials}
              onChange={(e) => setTrials(Number(e.target.value))}
              className="w-24 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-gray-100"
            />
          </label>
          <label className="text-xs text-gray-400">
            <span className="block mb-1">Slippage (bps)</span>
            <input
              type="number" min={0} max={100} value={slippage}
              onChange={(e) => setSlippage(Number(e.target.value))}
              className="w-24 bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-sm text-gray-100"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-400 pb-1.5">
            <input type="checkbox" checked={useNews}
                   onChange={(e) => setUseNews(e.target.checked)}
                   className="accent-indigo-500" />
            Use news sentiment
          </label>
          <div className="flex gap-2 ml-auto">
            {(['scan', 'backtest', 'walkforward'] as Tab[]).map((t) => (
              <Button
                key={t}
                variant={tab === t ? 'primary' : 'secondary'}
                size="sm"
                loading={loading && tab === t}
                onClick={() => { setTab(t); run(t); }}
              >
                {t === 'scan' ? 'Today' : t === 'backtest' ? 'Backtest' : 'Walk forward'}
              </Button>
            ))}
          </div>
        </div>
      </Card>

      {error && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* ── Scan ── */}
      {tab === 'scan' && scanResult && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard label="Bar scored" value={scanResult.date} sub="most recent close" />
            <StatCard label="Regime" value={scanResult.regime}
              sub={`held ${scanResult.regime_stability} bars`} />
            <StatCard label="Actionable proposals" value={String(scanResult.actionable)}
              sub={`of ${scanResult.proposals.length} scored`}
              color={scanResult.actionable > 0 ? 'green' : 'default'} />
            <StatCard label="News source" value={scanResult.news_source}
              sub={scanResult.news_is_synthetic ? 'synthetic — carries no information' : 'archive'}
              color={scanResult.news_is_synthetic ? 'yellow' : 'default'} />
          </div>

          {scanResult.news_is_synthetic && (
            <div className="rounded-lg border border-amber-800 bg-amber-900/20 px-4 py-3 text-sm text-amber-200 flex gap-2">
              <FlaskConical className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                No news archive is loaded, so headlines come from the synthetic
                provider. It is generated from past returns and seeded noise and
                is non-predictive by construction — treat the news evidence line
                as a wiring demonstration, not a signal. Drop a{' '}
                <code className="text-amber-100">data/news.jsonl</code> file in to
                switch to real headlines.
              </span>
            </div>
          )}

          <Card
            title="Every symbol, scored and decomposed"
            subtitle="Expand a row to see the contributions that sum to its score"
          >
            <div className="-mx-5 -mb-5">
              <div className="hidden sm:flex items-center gap-3 px-3 py-2 text-xs text-gray-500 border-b border-gray-700">
                <span className="w-4" />
                <span className="w-16">Symbol</span>
                <span className="w-4" />
                <span className="w-14">Action</span>
                <span className="w-20">Score</span>
                <span className="flex-1">Detail</span>
              </div>
              {shown.map((p) => (
                <ProposalRow
                  key={p.symbol}
                  p={p}
                  open={openRow === p.symbol}
                  onToggle={() => setOpenRow(openRow === p.symbol ? null : p.symbol)}
                />
              ))}
            </div>
          </Card>

          {config && (
            <Card title="How the score is built"
                  subtitle={`Weight set for the ${scanResult.regime} regime · weights ${config.weights_hash}`}>
              <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
                {config.features.map((f) => (
                  <div key={f.name} className="flex justify-between gap-3 border-b border-gray-800 pb-1.5">
                    <div>
                      <span className="text-gray-200 capitalize">{f.name}</span>
                      <p className="text-xs text-gray-500">{f.description}</p>
                    </div>
                    <span className="text-gray-400 tabular-nums shrink-0">
                      {scanResult.regime_weights
                        ? num(scanResult.regime_weights[f.name] ?? 0, 2)
                        : '—'}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-gray-500">
                A long needs a score of {num(config.entry_threshold, 2)}; a short
                needs {num(config.short_threshold, 2)} against it, because shorts
                carry borrow cost and unbounded loss. Stops sit{' '}
                {num(config.stop_atr_multiple, 1)}× the ATR proxy from entry and
                targets are placed to clear {num(config.target_risk_reward, 1)}R
                after costs.
              </p>
            </Card>
          )}
        </div>
      )}

      {/* ── Backtest ── */}
      {tab === 'backtest' && report && <ReportBody report={report} />}

      {/* ── Walk forward ── */}
      {tab === 'walkforward' && wf && (
        <div className="space-y-6">
          <div className="rounded-xl border border-gray-700 bg-gray-800 p-4 text-sm text-gray-300">
            {wf.reading_guide}
          </div>
          <div>
            <h2 className="text-sm font-semibold text-gray-400 mb-2 uppercase tracking-wide">
              In sample — contaminated, shown for contrast
            </h2>
            <ReportBody report={wf.in_sample} />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-indigo-300 mb-2 uppercase tracking-wide">
              Out of sample — the number that counts
            </h2>
            <ReportBody report={wf.out_of_sample} />
          </div>
        </div>
      )}

      {loading && !scanResult && !report && !wf && (
        <p className="text-sm text-gray-500">Running…</p>
      )}
    </Layout>
  );
}
