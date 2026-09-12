import { useEffect, useState } from 'react';

export type BinanceTicker = { price: number; changePct: number; eventTime: number };
export type TickerStatus = 'connecting' | 'live' | 'reconnecting';

// Binance's market-data-only host; stream.binance.com returns HTTP 451 in restricted regions.
const STREAM_URL = 'wss://data-stream.binance.vision/ws';

// Public Binance spot 24h ticker stream (no credentials). Reconnects with capped backoff.
export function useBinanceTicker(symbol = 'btcusdt') {
  const [ticker, setTicker] = useState<BinanceTicker | null>(null);
  const [status, setStatus] = useState<TickerStatus>('connecting');

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(`${STREAM_URL}/${symbol.toLowerCase()}@ticker`);
      ws.onopen = () => { attempts = 0; setStatus('live'); };
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          const price = Number(m.c);
          if (Number.isFinite(price)) setTicker({ price, changePct: Number(m.P), eventTime: Number(m.E) });
        } catch { /* ignore malformed frames */ }
      };
      ws.onerror = () => ws?.close();
      ws.onclose = () => {
        if (closed) return;
        setStatus('reconnecting');
        retry = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempts++));
      };
    };

    connect();
    return () => { closed = true; clearTimeout(retry); ws?.close(); };
  }, [symbol]);

  return { ticker, status };
}
