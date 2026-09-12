import api from './client';
import type {
  SimulationResult,
  CompareResult,
  SavingsResult,
  SimulateFormData,
} from '../types';

export async function simulate(data: SimulateFormData): Promise<SimulationResult> {
  const res = await api.post<SimulationResult>('/portfolio/simulate', data);
  return res.data;
}

export async function compareAll(data: SimulateFormData): Promise<CompareResult> {
  const res = await api.post<CompareResult>('/portfolio/compare', data);
  return res.data;
}

export interface SavingsRequest {
  monthly_take_home: number;
  monthly_essentials?: number;
  high_interest_debt?: number;
  emergency_fund?: number;
}

export async function savingsCapacity(data: SavingsRequest): Promise<SavingsResult> {
  const res = await api.post<SavingsResult>('/portfolio/savings', data);
  return res.data;
}

export async function getQuestions(): Promise<any[]> {
  const res = await api.get('/portfolio/questions');
  return res.data;
}

export interface QuestionnaireAnswers {
  drop_reaction: number;
  experience: number;
  income_stability: number;
  withdrawal_risk: number;
  priority: number;
}

export async function scoreQuestionnaire(answers: QuestionnaireAnswers) {
  const res = await api.post('/portfolio/questionnaire', answers);
  return res.data;
}
