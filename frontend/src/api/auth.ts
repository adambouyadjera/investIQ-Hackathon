import api from './client';
import type { User } from '../types';

export interface LoginData {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  date_of_birth: string;
  citizenship_attested: boolean;
  age_attested: boolean;
  terms_attested: boolean;
  monthly_income?: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(data: LoginData): Promise<TokenResponse> {
  const form = new URLSearchParams();
  form.append('username', data.email);
  form.append('password', data.password);
  const res = await api.post<TokenResponse>('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return res.data;
}

export async function register(data: RegisterData): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/register', data);
  return res.data;
}

export async function getMe(): Promise<User> {
  const res = await api.get<User>('/auth/me');
  return res.data;
}

/** Start a throwaway demo session. No credentials collected. */
export async function startGuestSession(): Promise<TokenResponse> {
  const res = await api.post<TokenResponse>('/auth/guest', {});
  return res.data;
}
