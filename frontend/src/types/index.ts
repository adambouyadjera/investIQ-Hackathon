export type RiskTier = 'conservative' | 'balanced' | 'aggressive';
export type Rebalance = 'never' | 'quarterly' | 'annual';

export interface User {
  id: string;
  email: string;
  username: string;
  date_of_birth: string;
  citizenship_attested: boolean;
  monthly_income: number | null;
  is_guest: boolean;
  created_at: string;
}

export interface AllocationItem {
  ticker: string;
  name: string;
  kind: string;
  weight: number;
  dollars: number;
  price: number;
  shares: number;
  whole_shares: number;
  expense_ratio: number;
}

export interface BacktestMetrics {
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

export interface BacktestPoint {
  date: string;
  balance: number;
  contributed: number;
  drawdown: number;
}

export interface Backtest {
  series: BacktestPoint[];
  final_balance: number;
  total_contributed: number;
  profit: number;
  profit_pct: number;
  fees_paid: number;
  metrics: BacktestMetrics;
}

export interface ProjectionPoint {
  month: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  contributed: number;
}

export interface Projection {
  series: ProjectionPoint[];
  final_p10: number;
  final_p50: number;
  final_p90: number;
  prob_beat_contributions: number;
  prob_hit_goal?: number;
}

export interface SimulationInputs {
  amount: number;
  horizon_years: number;
  risk: RiskTier;
  risk_label: string;
  monthly_contribution: number;
  rebalance: Rebalance;
  extra_fee: number;
  goal: number | null;
}

export interface SimulationResult {
  inputs: SimulationInputs;
  data_source: string;
  history_start: string;
  history_end: string;
  allocation: AllocationItem[];
  equity_share: number;
  horizon_factor: number;
  blended_expense_ratio: number;
  backtest: Backtest;
  projection: Projection;
  disclaimer: string;
}

export interface CompareResult {
  data_source: string;
  results: Record<RiskTier, SimulationResult>;
}

export interface SavingsResult {
  monthly_take_home: number;
  monthly_essentials: number;
  monthly_surplus: number;
  recommended_monthly_investment: number;
  recommended_annual_investment: number;
  effective_savings_rate: number;
  emergency_fund_target: number;
  emergency_fund_gap: number;
  warnings: string[];
}

export interface Scenario {
  id: string;
  name: string;
  risk_tier: RiskTier;
  amount: number;
  horizon_years: number;
  monthly_contribution: number;
  extra_fee: number;
  goal: number | null;
  result_json: SimulationResult | null;
  created_at: string;
}

export interface Quote {
  price: number;
  change_pct?: number;
  source: string;
}

export interface QuotesResponse {
  quotes: Record<string, Quote>;
  last_updated: string | null;
  market_open: boolean;
}

export interface SimulateFormData {
  amount: number;
  horizon_years: number;
  risk: RiskTier;
  monthly_contribution: number;
  rebalance: Rebalance;
  extra_fee: number;
  goal?: number;
}
