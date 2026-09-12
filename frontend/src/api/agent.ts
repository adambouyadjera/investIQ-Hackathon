import api from './client';

/** One weighted input to a decision. Contributions sum exactly to raw_score. */
export interface Evidence {
  name: string;
  raw: number;
  weight: number;
  contribution: number;
  direction: 'bullish' | 'bearish' | 'neutral';
  note: string;
}

export interface NewsDriver {
  text: string;
  published_at: string;
  source: string;
  polarity: number;
  decay: number;
  contribution: number;
  matched_terms: string;
}

export interface NewsScore {
  symbol: string;
  as_of: string;
  value: number;
  raw_value: number;
  coverage: number;
  source: string;
  thin_coverage: boolean;
  lexicon_version: string;
  drivers: NewsDriver[];
}

export interface Intent {
  symbol: string;
  side: 'long' | 'short';
  entry: number;
  stop: number;
  target_1: number;
  target_2: number;
  stop_distance: number;
  risk_reward: number;
  strategy: string;
  invalidation: string;
}

export interface Proposal {
  symbol: string;
  as_of: string;
  regime: string;
  regime_stability: number;
  raw_score: number;
  conviction: number;
  score: number;
  action: 'long' | 'short' | 'flat';
  evidence: Evidence[];
  rationale: string;
  weights_version: string;
  weights_hash: string;
  intent?: Intent;
  news?: NewsScore;
  skip_reason?: string;
}

export interface ScanResult {
  date: string;
  regime: string;
  regime_stability: number;
  regime_weights: Record<string, number> | null;
  news_source: string;
  news_is_synthetic: boolean;
  proposals: Proposal[];
  actionable: number;
  weights_hash: string;
  policy_hash: string;
  live_trading_supported: boolean;
  disclaimer: string;
}

export interface AgentConfig {
  live_trading_supported: boolean;
  weights_version: string;
  weights_hash: string;
  policy_hash: string;
  entry_threshold: number;
  short_threshold: number;
  stop_atr_multiple: number;
  target_risk_reward: number;
  max_chase_atr: number;
  regime_weights: Record<string, Record<string, number>>;
  features: { name: string; description: string }[];
  risk_limits: {
    risk_per_trade: number;
    max_concentration: number;
    max_open_risk: number;
    max_positions: number;
    min_risk_reward: number;
  };
  default_costs: Record<string, number>;
  disclaimer: string;
}

export interface Metrics {
  cagr: number;
  volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  best_year: number;
  worst_year: number;
  positive_months: number;
  var_95: number;
}

export interface BenchmarkComparison {
  strategy: Metrics;
  benchmark: Metrics;
  strategy_total_return: number;
  benchmark_total_return: number;
  excess_cagr: number;
  alpha_annualized: number;
  beta: number;
  tracking_error: number;
  information_ratio: number | null;
  up_capture: number | null;
  down_capture: number | null;
  drawdown_advantage: number;
  beat_benchmark: boolean;
}

export interface Significance {
  sharpe_per_period: number;
  sharpe_annualized: number;
  skew?: number;
  kurtosis?: number;
  n_observations: number;
  n_trials: number;
  threshold_sharpe: number | null;
  threshold_sharpe_annualized?: number;
  deflated_sharpe: number | null;
  verdict: string;
}

export interface BacktestReport {
  window: { start: string; end: string; bars: number; years: number };
  config: Record<string, unknown>;
  news_source: string;
  broker: {
    initial_cash: number;
    final_equity: number;
    net_profit: number;
    return_pct: number;
    closed_trades: number;
    win_rate: number;
    profit_factor: number | null;
    avg_win: number;
    avg_loss: number;
    total_costs: number;
    borrow_paid: number;
    cost_drag_pct: number;
    open_positions: number;
    live_trading_supported: boolean;
  };
  metrics: Metrics | null;
  benchmark: BenchmarkComparison;
  significance: Significance;
  risk: {
    policy_hash: string;
    weights_hash: string;
    vetoes: Record<string, number>;
    veto_total: number;
    breaker_events: {
      date: string; action: string; breakers: string[];
      detail: string; equity: number;
    }[];
  };
  equity_curve: { date: string; strategy: number; benchmark: number }[];
  caveats: string[];
  disclaimer: string;
  journal_summary?: Record<string, number>;
  recent_decisions?: Record<string, unknown>[];
}

export interface WalkForwardReport {
  split: string;
  in_sample: BacktestReport;
  out_of_sample: BacktestReport;
  reading_guide: string;
  disclaimer: string;
}

export interface BacktestRequest {
  start?: string;
  end?: string;
  initial_cash?: number;
  benchmark_symbol?: string;
  max_new_per_bar?: number;
  use_news?: boolean;
  n_trials?: number;
  commission_per_share?: number;
  commission_min?: number;
  half_spread_bps?: number;
  slippage_bps?: number;
  annual_borrow_rate?: number;
}

export interface RegimeHistory {
  symbol: string;
  series: { date: string; regime: string; stability: number }[];
  current: string;
  current_stability: number;
  counts: Record<string, number>;
  min_stability_to_trade: number;
}

export async function getAgentConfig(): Promise<AgentConfig> {
  const res = await api.get<AgentConfig>('/agent/config');
  return res.data;
}

export async function scan(body: Record<string, unknown> = {}): Promise<ScanResult> {
  const res = await api.post<ScanResult>('/agent/scan', body);
  return res.data;
}

export async function backtest(body: BacktestRequest = {}): Promise<BacktestReport> {
  const res = await api.post<BacktestReport>('/agent/backtest', body);
  return res.data;
}

export async function walkForward(
  body: BacktestRequest & { split?: string } = {},
): Promise<WalkForwardReport> {
  const res = await api.post<WalkForwardReport>('/agent/walk-forward', body);
  return res.data;
}

export async function getRegimeHistory(days = 180): Promise<RegimeHistory> {
  const res = await api.get<RegimeHistory>(`/agent/regime?days=${days}`);
  return res.data;
}
