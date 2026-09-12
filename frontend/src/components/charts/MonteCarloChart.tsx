import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
  Legend,
} from 'recharts';
import type { Projection } from '../../types';

interface Props {
  projection: Projection;
  goal?: number | null;
}

function fmt(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

export function MonteCarloChart({ projection, goal }: Props) {
  // Downsample to monthly for performance (show every 3rd month)
  const data = projection.series.filter((_, i) => i % 3 === 0 || i === projection.series.length - 1);

  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="p10Grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="p50Grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="p90Grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="month"
            tickFormatter={(v: number) => `Y${Math.floor(v / 12)}`}
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            axisLine={{ stroke: '#374151' }}
            tickLine={false}
            interval={Math.floor(data.length / 5)}
          />
          <YAxis
            tickFormatter={fmt}
            tick={{ fill: '#9ca3af', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af', fontSize: 12 }}
            labelFormatter={(v: any) => `Month ${v} (Year ${Math.floor(v / 12)})`}
            formatter={(val: any, name: any) => [fmt(val), name]}
          />
          <Legend
            formatter={(value) => (
              <span style={{ color: '#9ca3af', fontSize: 12 }}>{value}</span>
            )}
          />
          {goal && (
            <ReferenceLine
              y={goal}
              stroke="#f59e0b"
              strokeDasharray="5 5"
              label={{ value: 'Goal', fill: '#f59e0b', fontSize: 11 }}
            />
          )}
          <Area
            type="monotone"
            dataKey="p90"
            name="Best case (90th)"
            stroke="#10b981"
            strokeWidth={1.5}
            fill="url(#p90Grad)"
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="p50"
            name="Median (50th)"
            stroke="#6366f1"
            strokeWidth={2}
            fill="url(#p50Grad)"
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="p10"
            name="Bad case (10th)"
            stroke="#ef4444"
            strokeWidth={1.5}
            fill="url(#p10Grad)"
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="contributed"
            name="Total Invested"
            stroke="#6b7280"
            strokeWidth={1}
            fill="none"
            dot={false}
            strokeDasharray="4 4"
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Final value callouts */}
      <div className="grid grid-cols-3 gap-3 mt-4">
        <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-400">Bad case (10th pct)</p>
          <p className="text-lg font-bold text-red-400">{fmt(projection.final_p10)}</p>
        </div>
        <div className="bg-indigo-900/20 border border-indigo-800/50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-400">Median (50th pct)</p>
          <p className="text-lg font-bold text-indigo-400">{fmt(projection.final_p50)}</p>
        </div>
        <div className="bg-emerald-900/20 border border-emerald-800/50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-400">Best case (90th pct)</p>
          <p className="text-lg font-bold text-emerald-400">{fmt(projection.final_p90)}</p>
        </div>
      </div>
    </div>
  );
}
