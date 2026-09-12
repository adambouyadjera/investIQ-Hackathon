/**
 * Theme state: dark, light, or follow the OS.
 *
 * The attribute is set on <html> by an inline script in index.html before
 * first paint, so there is no flash of the wrong theme on load. This module
 * only handles changes made after the app mounts.
 */
import { useSyncExternalStore } from 'react';

export type Theme = 'dark' | 'light' | 'system';

const KEY = 'theme';
const listeners = new Set<() => void>();

function read(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'dark' || v === 'light' || v === 'system') return v;
  } catch {
    /* localStorage unavailable (private mode, embedded webview) */
  }
  return 'system';
}

let current: Theme = read();

export function resolve(theme: Theme): 'dark' | 'light' {
  if (theme !== 'system') return theme;
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function apply(theme: Theme) {
  const resolved = resolve(theme);
  document.documentElement.setAttribute('data-theme', resolved);
  document.documentElement.style.colorScheme = resolved;
}

export function setTheme(theme: Theme) {
  current = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* ignore write failures; the theme still applies for this session */
  }
  apply(theme);
  listeners.forEach((l) => l());
}

export function cycleTheme() {
  const order: Theme[] = ['dark', 'light', 'system'];
  setTheme(order[(order.indexOf(current) + 1) % order.length]);
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const mq = window.matchMedia('(prefers-color-scheme: light)');
  const onSystemChange = () => {
    if (current === 'system') {
      apply(current);
      listeners.forEach((l) => l());
    }
  };
  mq.addEventListener('change', onSystemChange);
  return () => {
    listeners.delete(cb);
    mq.removeEventListener('change', onSystemChange);
  };
}

export function useTheme() {
  const theme = useSyncExternalStore(
    subscribe,
    () => current,
    () => 'dark' as Theme,
  );
  return { theme, resolved: resolve(theme), setTheme, cycleTheme };
}
