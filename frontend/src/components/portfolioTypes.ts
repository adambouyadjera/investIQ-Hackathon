export type Risk = 'low' | 'medium' | 'high';

export type Explanation = {
  summary: string; market: string;
  news: { title: string; url: string; source: string; published_at: string | null; tone: string }[]; news_note: string;
  price_movement: string; indicators: string; fundamentals: string; volatility: string; risk_factors: string[];
  why_asset: string; alternatives: { ticker: string; name: string; score: number; status: string; reason: string }[];
  why_amount: string; holding_period: string; downside: string; sell_conditions: string[]; strategy_change: string[];
  price_note: string; disclaimer: string;
};

export type PTrade = {
  id: string; time: string; ticker: string; name: string; kind: string; action: 'BUY' | 'SELL'; shares: number; price: number;
  value: number; cash_before: number; cash_after: number; portfolio_before: number; portfolio_after: number;
  realized_pnl: number | null; pnl: number | null; pnl_type: 'realized' | 'unrealized' | 'closed'; reason: string; simulated: boolean; replayed?: boolean;
  explanation: Explanation;
};

export type Holding = { ticker: string; name: string; kind: string; shares: number; avg_cost: number; price: number; value: number; unrealized_pnl: number; unrealized_pct: number };

export type ConfiguredPortfolio = {
  configured: true; simulated: true; enabled: boolean; status: 'paused' | 'waiting' | 'holding' | 'cash'; created_at: string;
  settings: { amount: number; risk: Risk; months: number; risk_label: string };
  deposits: number; cash: number; invested: number; portfolio_value: number; total_return: number; total_return_pct: number;
  holdings: Holding[]; strategy: { summary: string; targets: { ticker: string; name: string; weight: number }[]; cash_reserve: number } | null;
  trades: PTrade[]; activity: { time: string; text: string }[];
  equity_history: { time: string; value: number; deposits?: number; trades: string[] }[];
  next_review: string | null; last_checked: string | null; review_minutes: number; replay: { start: string; end: string; days: number } | null; market_open: boolean; next_market_open: string;
  error: string | null; price_note: string; disclaimer: string;
};

export type Portfolio = { configured: false } | ConfiguredPortfolio;

const abs$ = (n: number) => `$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const usd = (n: number) => `${n < 0 ? '−' : ''}${abs$(n)}`;
export const signedUsd = (n: number) => `${n > 0.004 ? '+' : n < -0.004 ? '−' : ''}${abs$(n)}`;
export const signedPct = (n: number) => `${n > 0.00004 ? '+' : n < -0.00004 ? '−' : ''}${Math.abs(n * 100).toFixed(2)}%`;
export const shares = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 4 });
export const dateTime = (iso: string) => new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
export const tone = (n: number) => (n < -0.004 ? 'rd-negative' : n > 0.004 ? 'rd-positive' : '');
export const apiError = (e: any, fallback: string): string => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : d?.message ?? fallback;
};
