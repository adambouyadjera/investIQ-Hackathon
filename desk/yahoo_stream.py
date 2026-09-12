"""Live Yahoo Finance ticks for the watchlist, one upstream connection shared by all viewers."""
import asyncio, json, math, ssl
from datetime import datetime, timezone
from .yahoo import WATCHLIST
URL='wss://streamer.finance.yahoo.com/?version=2'

def normalize_tick(m):
    symbol=m.get('id')
    if symbol not in WATCHLIST:return None
    try:price=float(m.get('price'))
    except (TypeError,ValueError):return None
    if not math.isfinite(price) or price<=0:return None
    change=m.get('change_percent')
    change=float(change) if isinstance(change,(int,float)) and math.isfinite(change) else None
    try:stamp=datetime.fromtimestamp(int(m['time'])/1000,timezone.utc).isoformat()
    except (KeyError,TypeError,ValueError,OverflowError,OSError):stamp=None
    return {'symbol':symbol,'price':price,'change_pct':change,'price_as_of':stamp,'currency':m.get('currency') or 'USD'}

class YahooStream:
    def __init__(self,symbols=WATCHLIST):
        self.symbols=list(symbols);self.latest={};self.listeners=set();self.task=None
    def publish(self,tick):
        self.latest[tick['symbol']]=tick
        for q in list(self.listeners):
            if q.full():  # slow viewer: drop its oldest tick rather than block everyone
                try:q.get_nowait()
                except asyncio.QueueEmpty:pass
            q.put_nowait(tick)
    def subscribe(self):
        q=asyncio.Queue(maxsize=100);self.listeners.add(q)
        if self.task is None or self.task.done():self.task=asyncio.create_task(self._run())
        return q
    def unsubscribe(self,q):
        self.listeners.discard(q)
        if not self.listeners and self.task:self.task.cancel();self.task=None
    async def _run(self):
        import certifi
        from websockets.asyncio.client import connect
        from yfinance.live import BaseWebSocket
        decode=BaseWebSocket(URL,verbose=False)._decode_message
        # certifi bundle: python.org macOS builds ship without system CA roots.
        ctx=ssl.create_default_context(cafile=certifi.where());delay=1
        while True:
            try:
                async with connect(URL,ssl=ctx,open_timeout=10) as ws:
                    sub=json.dumps({'subscribe':self.symbols});await ws.send(sub);delay=1
                    heartbeat=asyncio.create_task(self._heartbeat(ws,sub))
                    try:
                        async for raw in ws:
                            try:tick=normalize_tick(decode(json.loads(raw).get('message','')))
                            except Exception:continue
                            if tick:self.publish(tick)
                    finally:heartbeat.cancel()
            except asyncio.CancelledError:raise
            except Exception:pass
            await asyncio.sleep(delay);delay=min(30,delay*2)
    @staticmethod
    async def _heartbeat(ws,sub):
        while True:
            await asyncio.sleep(15);await ws.send(sub)

STREAM=YahooStream()
