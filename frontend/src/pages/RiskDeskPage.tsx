import { useEffect, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import {
  evaluateRisk,
  getRiskPolicy,
  type RiskRequest,
  type RiskResult,
  type RiskPolicy,
} from '../api/risk';
import { Check, X, ShieldAlert, TriangleAlert } from 'lucide-react';

const PRESETS: { label: string; hint: string; patch: Partial<RiskRequest> }[] = [
  {
    label: 'Flat account',
    hint: 'No breakers active',
    patch: { equity: 2000, day_start_equity: 2000, week_start_equity: 2000 },
  },
  {
    label: 'Down 2% today',
    hint: 'Half size',
    patch: { equity: 1960, day_start_equity: 2000, week_start_equity: 2000 },
  },
  {
    label: 'Down 3.5% today',
    hint: 'Flatten',
    patch: { equity: 1930, day_start_equity: 2000, week_start_equity: 2000 },
  },
  {
    label: 'Down 6% this week',
    hint: 'No new entries',
    patch: { equity: 1880, day_start_equity: 1880, week_start_equity: 2000 },
  },
  {
    label: 'Down 10% from peak',
    hint: 'Full stop',
    patch: {
      equity: 1800, peak_equity: 2000, day_start_equity: 1800,
      week_start_equity: 1800, month_start_equity: 1800,
    },
  },
];

const DEFAULTS: RiskRequest = {
  equity: 2000,
  peak_equity: 2000,
  day_start_equity: 2000,
  week_start_equity: 2000,
  month_start_equity: 2000,
  open_risk: 0,
  open_position_count: 0,
  symbol: 'DEMO',
  side: 'long',
  entry: 50,
  stop: 49,
  target_1: 52,
  target_2: 53,
  strategy: 'ema_cross',
  regime: 'calm',
  regime_stability: 3,
  strategy_permitted: true,
  bar_closed: true,
  cost_per_share: 0,
};

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
const pct = (n: number) => `${(n * 100).toFixed(2)}%`;
const signed = (n: number) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`;

const CHECK_LABELS: Record<string, string> = {
  block_state: 'Trading block file',
  fresh_state: 'Account data freshness',
  closed_bar: 'Signal from a closed bar',
  regime_known: 'Regime label valid',
  regime_stable: 'Regime stability',
  strategy_permitted: 'Strategy validated for regime',
  protection: 'Stop, targets and reward',
  breakers: 'Circuit breakers',
  position_count: 'Open position count',
  sizing: 'Position sizing',
  final_ceiling: 'Final 1% ceiling re-check',
};

export default function RiskDeskPage() {
  const [form, setForm] = useState<RiskRequest>(DEFAULTS);
  const [result, setResult] = useState<RiskResult | null>(null);
  const [policy, setPolicy] = useState<RiskPolicy | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getRiskPolicy().then(setPolicy).catch(() => {});
  }, []);

  async function run(next: RiskRequest = form) {
    setLoading(true);
    setError('');
    try {
      setResult(await evaluateRisk(next));
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(
        Array.isArray(detail)
          ? detail.map((d: any) => d.message ?? d.msg).join(' · ')
          : detail || 'Could not reach the risk engine.',
      );
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    run(DEFAULTS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function set<K extends keyof RiskRequest>(key: K, value: RiskRequest[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function applyPreset(patch: Partial<RiskRequest>) {
    const next = { ...form, ...patch };
    setForm(next);
    run(next);
  }

  const num = (key: keyof RiskRequest, label: string, step = 1) => (
    <label className="block">
      <span className="text-xs text-gray-400">{label}</span>
      <input
        type="number"
        step={step}
        value={form[key] as number}
        onChange={(e) => set(key, Number(e.target.value) as any)}
        className="mt-1 w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2
                   text-sm text-gray-100 tabular focus:border-indigo-500 focus:outline-none"
      />
    </label>
  );

  return (
    <Layout>
      <div className="space-y-6">
        <header>
          <h1 className="text-2xl font-semibold text-gray-100">Risk desk</h1>
          <p className="text-sm text-gray-400 mt-1 max-w-2xl">
            A strategy may propose a trade. It may never place one. Every proposal
            is sized from its stop distance and refused by the first check it
            fails. No broker is connected and no order is placed.
          </p>
        </header>

        {/* Scenario presets */}
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => applyPreset(p.patch)}
              className="px-3 py-2 rounded-lg border border-gray-700 bg-gray-800
                         hover:border-indigo-600 text-left transition-colors"
            >
              <span className="block text-xs font-medium text-gray-200">{p.label}</span>
              <span className="block text-xs text-gray-500">{p.hint}</span>
            </button>
          ))}
        </div>

        <div className="grid lg:grid-cols-[minmax(0,340px)_1fr] gap-6 items-start">
          {/* ── Inputs ── */}
          <Card className="pt-5 space-y-5">
            <div>
              <h2 className="text-sm font-semibold text-gray-200 mb-3">Account</h2>
              <div className="grid grid-cols-2 gap-3">
                {num('equity', 'Current equity')}
                {num('peak_equity', 'Peak equity')}
                {num('day_start_equity', 'Day start')}
                {num('week_start_equity', 'Week start')}
                {num('month_start_equity', 'Month start')}
                {num('open_position_count', 'Open positions')}
              </div>
            </div>

            <div>
              <h2 className="text-sm font-semibold text-gray-200 mb-3">Proposal</h2>
              <div className="grid grid-cols-2 gap-3">
                {num('entry', 'Entry', 0.01)}
                {num('stop', 'Stop', 0.01)}
                {num('target_1', 'Target 1', 0.01)}
                {num('target_2', 'Target 2', 0.01)}
                {num('cost_per_share', 'Cost / share', 0.01)}
                <label className="block">
                  <span className="text-xs text-gray-400">Regime</span>
                  <select
                    value={form.regime}
                    onChange={(e) => set('regime', e.target.value as any)}
                    className="mt-1 w-full rounded-lg bg-gray-800 border border-gray-700
                               px-3 py-2 text-sm text-gray-100 focus:border-indigo-500
                               focus:outline-none"
                  >
                    <option value="calm">Calm</option>
                    <option value="volatile">Volatile</option>
                    <option value="bear">Bear</option>
                  </select>
                </label>
              </div>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={form.bar_closed}
                  onChange={(e) => set('bar_closed', e.target.checked)}
                  className="accent-current"
                />
                Signal came from a closed bar
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={form.strategy_permitted}
                  onChange={(e) => set('strategy_permitted', e.target.checked)}
                  className="accent-current"
                />
                Strategy validated for this regime
              </label>
              <label className="block">
                <span className="text-xs text-gray-400">
                  Regime stability — {form.regime_stability} of 3 bars
                </span>
                <input
                  type="range"
                  min={0}
                  max={3}
                  value={form.regime_stability}
                  onChange={(e) => set('regime_stability', Number(e.target.value))}
                  className="mt-1 w-full accent-current"
                />
              </label>
            </div>

            <Button onClick={() => run()} disabled={loading} className="w-full">
              {loading ? 'Evaluating…' : 'Run the gate'}
            </Button>
          </Card>

          {/* ── Results ── */}
          <div className="space-y-6">
            {error && (
              <Card className="pt-4 border-red-700 bg-red-900/30">
                <p className="text-sm text-red-300">{error}</p>
              </Card>
            )}

            {result && (
              <>
                <Card className={`pt-5 ${result.approved ? '' : 'border-red-700'}`}>
                  <div className="flex items-start gap-3">
                    {result.approved ? (
                      <Check className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                    ) : (
                      <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0">
                      <p className={`font-semibold ${result.approved ? 'text-emerald-400' : 'text-red-400'}`}>
                        {result.approved ? 'Risk cleared' : result.veto_code}
                      </p>
                      <p className="text-sm text-gray-400 mt-0.5">
                        {result.approved
                          ? `${result.quantity} shares, ${money(result.position_value)} position`
                          : result.veto_reason}
                      </p>
                    </div>
                  </div>

                  {result.approved && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 pt-5 border-t border-gray-700">
                      <Metric label="Quantity" value={String(result.quantity)} />
                      <Metric label="Planned loss" value={money(result.planned_loss)} />
                      <Metric label="Risk of equity" value={pct(result.risk_pct)} />
                      <Metric label="Concentration" value={pct(result.concentration_pct)} />
                    </div>
                  )}
                </Card>

                <div className="grid sm:grid-cols-4 gap-3">
                  <Delta label="Today" value={result.account.daily_pct} />
                  <Delta label="This week" value={result.account.weekly_pct} />
                  <Delta label="This month" value={result.account.monthly_pct} />
                  <Delta label="From peak" value={result.account.drawdown_pct} />
                </div>

                {result.active_breakers.length > 0 && (
                  <Card className="pt-4">
                    <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
                      <TriangleAlert className="w-4 h-4 text-yellow-400" />
                      Active circuit breakers
                    </h3>
                    <ul className="space-y-2">
                      {result.active_breakers.map((b) => (
                        <li key={b.name} className="flex items-baseline gap-3 text-sm">
                          <span className="mono text-xs text-yellow-400 shrink-0">
                            {b.action}
                          </span>
                          <span className="text-gray-400">{b.detail}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}

                <Card className="pt-4">
                  <h3 className="text-sm font-semibold text-gray-200 mb-3">
                    Pre-trade gate
                  </h3>
                  <ol className="space-y-1">
                    {result.checks.map((c, i) => (
                      <li
                        key={c.name}
                        className="flex items-baseline gap-3 py-1.5 border-b border-gray-800 last:border-0"
                      >
                        <span className="mono text-xs text-gray-500 w-5 shrink-0">
                          {String(i + 1).padStart(2, '0')}
                        </span>
                        {c.passed ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        ) : (
                          <X className="w-3.5 h-3.5 text-red-400 shrink-0" />
                        )}
                        <span className="text-sm text-gray-300 flex-1">
                          {CHECK_LABELS[c.name] ?? c.name}
                        </span>
                        <span
                          className={`mono text-xs shrink-0 ${
                            c.passed ? 'text-gray-500' : 'text-red-400'
                          }`}
                        >
                          {c.code}
                        </span>
                      </li>
                    ))}
                  </ol>
                  {!result.approved && (
                    <p className="text-xs text-gray-500 mt-3">
                      The gate stops at the first refusal. Checks after it never ran.
                    </p>
                  )}
                </Card>

                {policy && (
                  <Card className="pt-4">
                    <div className="flex items-baseline justify-between mb-3 gap-4">
                      <h3 className="text-sm font-semibold text-gray-200">
                        Circuit breaker cascade
                      </h3>
                      <span className="mono text-xs text-gray-500">
                        policy {policy.policy_hash}
                      </span>
                    </div>
                    <table className="w-full text-sm">
                      <tbody>
                        {policy.cascade.map((r) => (
                          <tr key={r.trigger} className="border-b border-gray-800 last:border-0">
                            <td className="py-2 pr-3 text-gray-500 text-xs whitespace-nowrap">
                              {r.scope}
                            </td>
                            <td className="py-2 pr-3 text-gray-300">{r.trigger}</td>
                            <td className="py-2 text-gray-400 text-right">{r.action}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="text-xs text-gray-500 mt-3">
                      When two breakers are active the strictest wins. Exactly −3.00%
                      halves size; −3.01% flattens. Missing or stale account data is a
                      refusal, never a default.
                    </p>
                  </Card>
                )}

                <p className="text-xs text-gray-500">{result.disclaimer}</p>
              </>
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-lg font-semibold text-gray-100 tabular mt-0.5">{value}</p>
    </div>
  );
}

function Delta({ label, value }: { label: string; value: number }) {
  const tone =
    value < 0 ? 'text-red-400' : value > 0 ? 'text-emerald-400' : 'text-gray-400';
  return (
    <Card className="pt-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-base font-semibold tabular mt-0.5 ${tone}`}>{signed(value)}</p>
    </Card>
  );
}
