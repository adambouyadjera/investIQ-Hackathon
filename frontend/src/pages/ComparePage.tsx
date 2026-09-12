import { useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { SimulateForm } from '../components/SimulateForm';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { compareAll } from '../api/portfolio';
import type { CompareResult, SimulateFormData, RiskTier, SimulationResult } from '../types';
import { BacktestChart } from '../components/charts/BacktestChart';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';

const TIER_COLORS: Record<RiskTier, string> = {
  conservative: '#3b82f6',
  balanced: '#6366f1',
  aggressive: '#a855f7',
};

const TIER_BADGE: Record<RiskTier, 'blue' | 'purple' | 'red'> = {
  conservative: 'blue',
  balanced: 'purple',
  aggressive: 'red',
};

function pct(n: number) { return `${(n * 100).toFixed(2)}%`; }
function money(n: number) {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function MetricsBar({ results }: { results: Record<RiskTier, SimulationResult> }) {
  const tiers: RiskTier[] = ['conservative', 'balanced', 'aggressive'];

  const charts = [
    { key: 'cagr', label: 'CAGR', fmt: pct, fromMetrics: true },
    { key: 'sharpe', label: 'Sharpe Ratio', fmt: (n: number) => n.toFixed(2), fromMetrics: true },
    { key: 'max_drawdown', label: 'Max Drawdown', fmt: pct, fromMetrics: true },
    { key: 'volatility', label: 'Volatility', fmt: pct, fromMetrics: true },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {charts.map(({ key, label, fmt: f }) => {
        const data = tiers.map((t) => ({
          name: results[t].inputs.risk_label,
          value: Math.abs((results[t].backtest.metrics as any)[key]),
          raw: (results[t].backtest.metrics as any)[key],
          tier: t,
        }));
        return (
          <Card key={key} title={label}>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(v) => f(key === 'max_drawdown' ? -v : v)} tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
                  formatter={(_val: any, _: any, props: any) => [f(props.payload.raw), label]}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {data.map((d) => (
                    <Cell key={d.tier} fill={TIER_COLORS[d.tier as RiskTier]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        );
      })}
    </div>
  );
}

export default function ComparePage() {
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleCompare(data: SimulateFormData) {
    setLoading(true);
    setError('');
    try {
      const res = await compareAll(data);
      setResult(res);
      setTimeout(() => document.getElementById('compare-results')?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Comparison failed.');
    } finally {
      setLoading(false);
    }
  }

  const tiers: RiskTier[] = ['conservative', 'balanced', 'aggressive'];

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Strategy Comparison</h1>
          <p className="text-gray-400 text-sm mt-1">
            Run all three risk tiers side-by-side with the same inputs.
          </p>
        </div>

        <Card title="Simulation Parameters">
          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}
          <SimulateForm onSubmit={handleCompare} loading={loading} />
        </Card>

        {result && (
          <div id="compare-results" className="flex flex-col gap-6">
            {/* Summary cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {tiers.map((tier) => {
                const r = result.results[tier];
                const m = r.backtest.metrics;
                return (
                  <Card key={tier}>
                    <div className="flex items-center justify-between mb-3">
                      <Badge color={TIER_BADGE[tier]}>{r.inputs.risk_label}</Badge>
                      <span className="text-xs text-gray-500">{(r.equity_share * 100).toFixed(0)}% equity</span>
                    </div>
                    <div className="flex flex-col gap-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Median end value</span>
                        <span className="text-emerald-400 font-mono">{money(r.projection.final_p50)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">CAGR</span>
                        <span className="text-gray-200 font-mono">{pct(m.cagr)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Sharpe</span>
                        <span className="text-gray-200 font-mono">{m.sharpe.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Max Drawdown</span>
                        <span className="text-red-400 font-mono">{pct(m.max_drawdown)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Volatility</span>
                        <span className="text-gray-200 font-mono">{pct(m.volatility)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Fees paid</span>
                        <span className="text-amber-400 font-mono">{money(r.backtest.fees_paid)}</span>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>

            {/* Metrics bar charts */}
            <MetricsBar results={result.results} />

            {/* Backtest overlays */}
            <Card title="Historical Balance — All Three Tiers" subtitle={`Data source: ${result.data_source}`}>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {tiers.map((tier) => (
                  <div key={tier}>
                    <p className="text-xs text-gray-400 mb-2 capitalize">{tier}</p>
                    <BacktestChart data={result.results[tier].backtest.series} />
                  </div>
                ))}
              </div>
            </Card>

            <p className="text-xs text-gray-600 text-center">
              {result.results.balanced.disclaimer}
            </p>
          </div>
        )}
      </div>
    </Layout>
  );
}
