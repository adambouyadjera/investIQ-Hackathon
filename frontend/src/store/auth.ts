import type { User } from '../types';
import { getMe } from '../api/auth';

let _user: User | null = null;
let _listeners: Array<() => void> = [];

function notify() {
  _listeners.forEach((l) => l());
}

export function getUser() {
  return _user;
}

export function setUser(u: User | null) {
  _user = u;
  notify();
}

export function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  _user = null;
  notify();
}

export function subscribe(fn: () => void) {
  _listeners.push(fn);
  return () => { _listeners = _listeners.filter((l) => l !== fn); };
}

export async function initializeAuth(): Promise<User | null> {
  const token = localStorage.getItem('access_token');
  if (!token) return null;
  try {
    const user = await getMe();
    _user = user;
    notify();
    return user;
  } catch {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    return null;
  }
}
