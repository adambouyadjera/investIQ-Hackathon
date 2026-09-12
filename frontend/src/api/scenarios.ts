import api from './client';
import type { Scenario, SimulationResult, RiskTier } from '../types';

export async function getScenarios(): Promise<Scenario[]> {
  const res = await api.get<Scenario[]>('/scenarios/');
  return res.data;
}

export async function saveScenario(data: {
  name: string;
  risk_tier: RiskTier;
  amount: number;
  horizon_years: number;
  monthly_contribution: number;
  extra_fee: number;
  goal?: number | null;
  result_json?: SimulationResult;
}): Promise<Scenario> {
  const res = await api.post<Scenario>('/scenarios/', data);
  return res.data;
}

export async function deleteScenario(id: string): Promise<void> {
  await api.delete(`/scenarios/${id}`);
}
