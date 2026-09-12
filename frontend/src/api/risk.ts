import api from './client';

export interface RiskRequest {
  equity: number;
  peak_equity?: number;
  day_start_equity?: number;
  week_start_equity?: number;
  month_start_equity?: number;
  open_risk?: number;
  open_position_count?: number;
  symbol?: string;
  side?: 'long' | 'short';
  entry: number;
  stop: number;
  target_1: number;
  target_2: number;
  strategy?: string;
  regime?: 'calm' | 'volatile' | 'bear';
  regime_stability?: number;
  strategy_permitted?: boolean;
  bar_closed?: boolean;
  cost_per_share?: number;
}

export interface GateCheck {
  name: string;
  passed: boolean;
  code: string;
  reason: string;
}

export interface ActiveBreaker {
  name: string;
  action: string;
  detail: string;
}

export interface RiskResult {
  approved: boolean;
  quantity: number;
  planned_loss: number;
  position_value: number;
  risk_pct: number;
  concentration_pct: number;
  risk_reward: number;
  stop_distance: number;
  veto_code: string;
  veto_reason: string;
  checks: GateCheck[];
  active_breakers: ActiveBreaker[];
  account: {
    equity: number;
    daily_pct: number;
    weekly_pct: number;
    monthly_pct: number;
    drawdown_pct: number;
  };
  policy_hash: string;
  disclaimer: string;
}

export interface CascadeRule {
  scope: string;
  trigger: string;
  threshold: number;
  action: string;
}

export interface RiskPolicy {
  policy_hash: string;
  risk_per_trade: number;
  max_concentration: number;
  max_open_risk: number;
  max_positions: number;
  min_risk_reward: number;
  cascade: CascadeRule[];
}

export async function evaluateRisk(data: RiskRequest): Promise<RiskResult> {
  const res = await api.post<RiskResult>('/risk/evaluate', data);
  return res.data;
}

export async function getRiskPolicy(): Promise<RiskPolicy> {
  const res = await api.get<RiskPolicy>('/risk/policy');
  return res.data;
}
