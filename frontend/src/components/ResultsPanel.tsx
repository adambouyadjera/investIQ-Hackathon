import { useState } from 'react';
import { BookmarkPlus, Download } from 'lucide-react';
import type { SimulationResult } from '../types';
import { StatCard, Card } from './ui/Card';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { BacktestChart } from './charts/BacktestChart';
import { MonteCarloChart } from './charts/MonteCarloChart';
import { AllocationChart } from './charts/AllocationChart';
import { DrawdownChart } from './charts/DrawdownChart';
import { saveScenario } from '../api/scenarios';

interface Props {
  result: SimulationResult;
}

function pct(n: number) {
  return `${(n * 100).toFixed(2)}%`;
}

function money(n: number) {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

const METRIC_TOOLTIPS: Record<string, string> = {
  cagr: 'Compound Annual Growth Rate — the smoothed annual return over the full backtest period.',
  volatility: 'Annualized standard deviation of daily returns. Higher = more price swings.',
  sharpe: 'Return per unit of total risk (3% risk-free rate). Above 1.0 is considered good.',
  sortino: 'Like Sharpe but only penalizes downside volatility. Better measure for most investors.',
  max_drawdown: 'Worst peak-to-trough decline. If this keeps you up at night, go more conservative.',
  calmar: 'CAGR divided by max drawdown. Measures return earned per unit of worst-case loss.',
  var_95: 'Value at Risk: worst 5% of daily return outcomes.',
};

export function ResultsPanel({ result }: Props) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const { inputs, backtest, projection, allocation } = result;
  const m = backtest.metrics;

  const riskColors = {
    conservative: 'blue',
    balanced: 'purple',
    aggressive: 'red',
  } as const;

  async function handleSave() {
    setSaving(true);
    try {
      const name = `${inputs.risk_label} — ${money(inputs.amount)}, ${inputs.horizon_years}yr`;
      await saveScenario({
        name,
        risk_tier: inputs.risk,
        amount: inputs.amount,
        horizon_years: inputs.horizon_years,
        monthly_contribution: inputs.monthly_contribution,
        extra_fee: inputs.extra_fee,
        goal: inputs.goal,
        result_json: result,
      });
      setSaved(true);
    } catch {
      // silent fail — user can retry
    } finally {
      setSaving(false);
    }
  }

  function handleExport() {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `portfolio-sim-${inputs.risk}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Badge color={riskColors[inputs.risk]}>{inputs.risk_label}</Badge>
          <span className="text-gray-400 text-sm">
            {money(inputs.amount)} · {inputs.horizon_years}yr horizon · data: {result.data_source}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={handleExport}>
            <Download className="w-4 h-4" />
            Export
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleSave}
            loading={saving}
            disabled={saved}
          >
            <BookmarkPlus className="w-4 h-4" />
            {saved ? 'Saved!' : 'Save'}
          </Button>
        </div>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Final Balance (median)"
          value={money(projection.final_p50)}
          sub={`vs ${money(backtest.total_contributed)} invested`}
          color="green"
        />
        <StatCard
          label="Backtest Profit"
          value={money(backtest.profit)}
          sub={pct(backtest.profit_pct)}
          color={backtest.profit >= 0 ? 'green' : 'red'}
        />
        <StatCard
          label="CAGR"
          value={pct(m.cagr)}
          sub="annualized return"
          tooltip={METRIC_TOOLTIPS.cagr}
        />
        <StatCard
          label="Max Drawdown"
          value={pct(m.max_drawdown)}
          sub="worst peak-to-trough"
          color="red"
          tooltip={METRIC_TOOLTIPS.max_drawdown}
        />
      </div>

      {/* Backtest chart */}
      <Card title="Historical Backtest" subtitle={`${result.history_start} → ${result.history_end}`}>
        <BacktestChart data={backtest.series} />
      </Card>

      {/* Two columns: allocation + metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card title="Portfolio Allocation">
          <AllocationChart allocation={allocation} />
          <table className="w-full text-sm mt-3">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-gray-700">
                <th className="pb-2">Ticker</th>
                <th className="pb-2">Name</th>
                <th className="pb-2 text-right">Weight</th>
                <th className="pb-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {allocation.map((a) => (
                <tr key={a.ticker} className="border-b border-gray-800 hover:bg-gray-750">
                  <td className="py-1.5 font-mono text-indigo-300">{a.ticker}</td>
                  <td className="py-1.5 text-gray-300 text-xs">{a.name}</td>
                  <td className="py-1.5 text-right text-gray-200">{pct(a.weight)}</td>
                  <td className="py-1.5 text-right text-emerald-400">{money(a.dollars)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div className="flex flex-col gap-4">
          {/* Risk metrics */}
          <Card title="Risk & Performance Metrics">
            <div className="grid grid-cols-2 gap-2 text-sm">
              {(
                [
                  ['Sharpe Ratio', m.sharpe.toFixed(2), METRIC_TOOLTIPS.sharpe],
                  ['Sortino Ratio', m.sortino.toFixed(2), METRIC_TOOLTIPS.sortino],
                  ['Volatility', pct(m.volatility), METRIC_TOOLTIPS.volatility],
                  ['Calmar Ratio', m.calmar.toFixed(2), METRIC_TOOLTIPS.calmar],
                  ['Best Year', pct(m.best_year), ''],
                  ['Worst Year', pct(m.worst_year), ''],
                  ['Positive Months', pct(m.positive_months), ''],
                  ['95% VaR (daily)', pct(m.var_95), METRIC_TOOLTIPS.var_95],
                ] as [string, string, string][]
              ).map(([label, val, tip]) => (
                <div key={label} className="flex justify-between items-center py-1 border-b border-gray-800" title={tip}>
                  <span className="text-gray-400 text-xs">{label}</span>
                  <span className="text-gray-200 font-mono">{val}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 text-xs text-gray-500">
              Equity share: {pct(result.equity_share)} · Expense ratio: {pct(result.blended_expense_ratio)}
            </div>
          </Card>

          {/* Fees */}
          <div className="bg-amber-900/20 border border-amber-800/50 rounded-xl p-4">
            <p className="text-xs text-amber-300 font-medium">Fees Paid Over History</p>
            <p className="text-2xl font-bold text-amber-400 mt-1">{money(backtest.fees_paid)}</p>
            <p className="text-xs text-gray-400 mt-1">
              Blended expense ratio: {pct(result.blended_expense_ratio)}/yr
            </p>
          </div>
        </div>
      </div>

      {/* Drawdown chart */}
      <Card title="Drawdown History" subtitle="How far below peak the portfolio was at each point">
        <DrawdownChart data={backtest.series} />
      </Card>

      {/* Monte Carlo projection */}
      <Card
        title="Forward Projection"
        subtitle={`${inputs.horizon_years}-year simulation · 2,000 bootstrapped paths`}
      >
        <MonteCarloChart projection={projection} goal={inputs.goal} />
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="bg-gray-900 rounded-lg p-3">
            <p className="text-xs text-gray-400">P(beats total invested)</p>
            <p className="text-xl font-bold text-emerald-400">
              {pct(projection.prob_beat_contributions)}
            </p>
          </div>
          {projection.prob_hit_goal !== undefined && (
            <div className="bg-gray-900 rounded-lg p-3">
              <p className="text-xs text-gray-400">P(hits your goal)</p>
              <p className="text-xl font-bold text-amber-400">
                {pct(projection.prob_hit_goal)}
              </p>
            </div>
          )}
        </div>
      </Card>

      <p className="text-xs text-gray-600 text-center">{result.disclaimer}</p>
    </div>
  );
}
