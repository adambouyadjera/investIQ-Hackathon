import { useId, useMemo, useState } from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceDot, CartesianGrid } from 'recharts';
import { type ConfiguredPortfolio, type PTrade, usd, signedUsd, signedPct, shares } from './portfolioTypes';

type Point = { t: number; pnl: number; value: number; trades: PTrade[] };
const RANGES: Record<string, number> = { '1D': 1, '1W': 7, '1M': 30, '3M': 91, '1Y': 365, All: 0 };
const GREEN = '#75b957', RED = '#e79486';
const axisMoney = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}$${Math.abs(v) >= 1000 ? `${(Math.abs(v) / 1000).toFixed(1)}k` : Math.abs(v).toFixed(0)}`;

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return <div className="rd-pchart-tip">
    <span>{new Date(p.t).toLocaleString()}</span>
    <strong style={{ color: p.pnl < 0 ? RED : GREEN }}>{signedUsd(p.pnl)}</strong>
    <span>Portfolio value {usd(p.value)}</span>
    {p.trades.map(t => <span key={t.id}>{t.action === 'BUY' ? 'Buy' : 'Sale'}: {shares(t.shares)} {t.ticker} ({usd(t.value)})</span>)}
  </div>;
}

export default function ProfitChart({ data, onSelect }: { data: ConfiguredPortfolio; onSelect: (t: PTrade) => void }) {
  const [range, setRange] = useState('All');
  const id = useId().replace(/:/g, '');
  const points = useMemo<Point[]>(() => {
    const byId = new Map(data.trades.map(t => [t.id, t]));
    const pts = data.equity_history.map(p => ({ t: Date.parse(p.time), value: p.value, pnl: p.value - (p.deposits ?? data.settings.amount),
      trades: p.trades.map(x => byId.get(x)).filter((x): x is PTrade => !!x) }));
    if (!pts.length) return pts;
    const start = pts[0].value - pts[0].pnl; // the original investment: profit/loss starts at $0
    return [{ t: Math.min(Date.parse(data.created_at), pts[0].t - 1000), value: start, pnl: 0, trades: [] }, ...pts];
  }, [data.equity_history, data.trades, data.created_at, data.settings.amount]);
  const last = points.at(-1)?.t ?? 0;
  const shown = points.filter(p => !RANGES[range] || p.t >= last - RANGES[range] * 86400000);
  const series = shown.length === 1 ? [shown[0], { ...shown[0], t: shown[0].t + 60000, trades: [] }] : shown;
  const values = series.map(p => p.pnl);
  const dataMax = Math.max(...values), dataMin = Math.min(...values);
  // Keep break-even centred with a sensible minimum range, so a few dollars of trading costs don't fill the whole chart.
  const span = Math.max(Math.abs(dataMax), Math.abs(dataMin), data.deposits * 0.005) * 1.2;
  // Gradients use each shape's own bounding box: the area always includes the $0 baseline, the line only its data.
  const areaTop = Math.max(0, dataMax), areaBottom = Math.min(0, dataMin);
  const areaSplit = areaTop === areaBottom ? 1 : areaTop / (areaTop - areaBottom);
  const lineSplit = dataMin >= 0 ? 1 : dataMax <= 0 ? 0 : dataMax / (dataMax - dataMin);
  const latest = series.at(-1);
  const multiDay = series.length > 1 && series[series.length - 1].t - series[0].t > 86400000;
  return <section className="rd-pchart" aria-labelledby={`${id}-title`}>
    <div className="rd-pchart-head">
      <h3 id={`${id}-title`}>Portfolio Profit Over Time</h3>
      <div className="rd-seg" role="group" aria-label="Time range">{Object.keys(RANGES).map(r =>
        <button key={r} className={range === r ? 'active' : ''} aria-pressed={range === r} onClick={() => setRange(r)}>{r}</button>)}</div>
    </div>
    <div className="rd-pchart-box">
      {series.length ? <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={series} margin={{ top: 22, right: 16, bottom: 4, left: 4 }}>
          <defs>
            <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
              <stop offset={areaSplit} stopColor={GREEN} stopOpacity={0.16}/><stop offset={areaSplit} stopColor={RED} stopOpacity={0.16}/>
            </linearGradient>
            <linearGradient id={`${id}-line`} x1="0" y1="0" x2="0" y2="1">
              <stop offset={lineSplit} stopColor={GREEN}/><stop offset={lineSplit} stopColor={RED}/>
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#2a2d27" vertical={false}/>
          <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} stroke="#6f7669" fontSize={11}
            tickFormatter={v => new Date(v).toLocaleString([], multiDay ? { month: 'short', day: 'numeric' } : { hour: 'numeric', minute: '2-digit' })}/>
          <YAxis domain={[-span, span]} stroke="#6f7669" fontSize={11} width={60} tickFormatter={axisMoney} allowDataOverflow/>
          <Tooltip content={<Tip/>}/>
          <ReferenceLine y={0} stroke="#8d947e" strokeDasharray="4 4" label={{ value: `Break-even (${usd(data.deposits)})`, position: 'insideTopLeft', fill: '#8f9784', fontSize: 11 }}/>
          <Area type="monotone" dataKey="pnl" baseValue={0} stroke={`url(#${id}-line)`} strokeWidth={2.5} fill={`url(#${id}-fill)`} isAnimationActive={false}/>
          {series.filter(p => p.trades.length).map(p => {
            const buy = p.trades.some(t => t.action === 'BUY'), sell = p.trades.some(t => t.action === 'SELL');
            const fill = buy && sell ? '#dbad53' : buy ? GREEN : RED;
            return <ReferenceDot key={p.t} x={p.t} y={p.pnl} r={6} fill={fill}
              shape={((s: { cx?: number; cy?: number }) => <circle cx={s.cx} cy={s.cy} r={6} fill={fill} stroke="#191a18" strokeWidth={2} style={{ cursor: 'pointer' }} onClick={() => onSelect(p.trades[0])}/>) as never}/>;
          })}
          {latest && <ReferenceDot x={latest.t} y={latest.pnl} r={5}
            shape={((s: { cx?: number; cy?: number }) => {
              // Latest value callout; pointer events pass through to any trade dot underneath.
              const cx = s.cx ?? 0, cy = s.cy ?? 0, w = 100, h = 40, color = latest.pnl < 0 ? RED : GREEN;
              const x = cx - w - 12 < 0 ? cx + 12 : cx - w - 12, y = cy < 60 ? cy + 10 : cy - h - 10;
              const basis = latest.value - latest.pnl;
              return <g pointerEvents="none">
                <circle cx={cx} cy={cy} r={5} fill={color} stroke="#191a18" strokeWidth={2}/>
                <rect x={x} y={y} width={w} height={h} rx={6} fill="#20211f" stroke="#393b36"/>
                <text x={x + w / 2} y={y + 17} textAnchor="middle" fill="#edeee9" fontSize={12}>{signedUsd(latest.pnl)}</text>
                <text x={x + w / 2} y={y + 32} textAnchor="middle" fill={color} fontSize={11}>{basis ? signedPct(latest.pnl / basis) : ''}</text>
              </g>;
            }) as never}/>}
        </AreaChart>
      </ResponsiveContainer> : null}
    </div>
    <p className="rd-news-note">Dots are trades — click one to see why. {data.price_note}</p>
  </section>;
}
