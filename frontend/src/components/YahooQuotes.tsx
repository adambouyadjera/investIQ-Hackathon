import { useEffect, useState } from 'react';
import api from '../api/client';
type Quote={symbol:string;name:string;price?:number;currency?:string;change_pct?:number|null;price_as_of?:string|null;bar_date?:string;url?:string;status:string;stale?:boolean};
type Data={quotes:Quote[];checked_at:string;note:string};
type Tick={symbol:string;price:number;change_pct:number|null;price_as_of:string|null;currency:string};
type StreamState='connecting'|'live'|'reconnecting';
const streamLabel:Record<StreamState,string>={connecting:'Connecting to live stream…',live:'Live · streaming ticks',reconnecting:'Stream interrupted · reconnecting'};
export default function YahooQuotes(){
 const [data,setData]=useState<Data|null>(null),[error,setError]=useState(''),[live,setLive]=useState<Record<string,Tick>>({}),[stream,setStream]=useState<StreamState>('connecting');
 async function load(){try{setData((await api.get('/research/yahoo')).data);setError('');}catch{setError('Yahoo Finance is unavailable.');}}
 useEffect(()=>{void load();const timer=setInterval(()=>void load(),300000);return()=>clearInterval(timer);},[]);
 useEffect(()=>{const ctrl=new AbortController();let delay=1000;
  const run=async()=>{while(!ctrl.signal.aborted){try{
   const res=await fetch('/api/research/yahoo/stream',{headers:{Authorization:`Bearer ${localStorage.getItem('access_token')??''}`},signal:ctrl.signal});
   // An expired token: let the axios interceptor refresh it, then retry.
   if(res.status===401){await api.get('/research/yahoo').catch(()=>{});throw new Error('auth');}
   if(!res.ok||!res.body)throw new Error('stream');
   setStream('live');delay=1000;
   const reader=res.body.pipeThrough(new TextDecoderStream()).getReader();let buf='';
   for(;;){const {value,done}=await reader.read();if(done)break;buf+=value;let i;
    while((i=buf.indexOf('\n\n'))>=0){const payload=buf.slice(0,i).split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('');buf=buf.slice(i+2);
     if(payload){try{const t=JSON.parse(payload) as Tick;setLive(p=>({...p,[t.symbol]:t}));}catch{/* skip malformed event */}}}}
  }catch{/* fall through to reconnect */}
  if(ctrl.signal.aborted)return;setStream('reconnecting');await new Promise(r=>setTimeout(r,delay));delay=Math.min(30000,delay*2);}};
  void run();return()=>ctrl.abort();},[]);
 return <section className="rd-news"><div className="rd-news-heading"><h2>Yahoo Finance watchlist</h2><span>{streamLabel[stream]}</span></div><p className="rd-news-note">Crypto, US equities and gold. Stocks and ETFs only tick during US market hours; otherwise the last session price is shown. The paper bot continues to use Binance BTC/USDT.</p>{error&&<p className="rd-feed-error" role="alert">{error} <button onClick={()=>void load()}>Retry</button></p>}{!data&&!error&&<p className="rd-news-note">Loading Yahoo Finance…</p>}<div className="rd-yahoo-grid">{data?.quotes.map(base=>{const tick=live[base.symbol];const q:Quote=tick?{...base,...tick,stale:false}:base;
 // Outside market hours Yahoo still pushes the last session's price; only call it live if it is recent.
 const t=tick&&tick.price_as_of&&Date.now()-Date.parse(tick.price_as_of)<120000?tick:null;return <article key={q.symbol}><div className="rd-news-meta"><strong>{q.symbol}</strong><span>{q.name}</span></div><div className="rd-yahoo-price">{q.price!==undefined?<a href={q.url} target="_blank" rel="noopener noreferrer">{q.price.toLocaleString('en-US',{maximumFractionDigits:2,minimumFractionDigits:2})} <small>{q.currency}</small></a>:<span>Unavailable</span>}{q.change_pct!=null&&<span className={q.change_pct<0?'rd-negative':'rd-positive'}>{q.change_pct>=0?'+':''}{q.change_pct.toFixed(2)}%</span>}</div><p className="rd-news-note">{t?<><span className="rd-tiny-dot"/> Live tick: {q.price_as_of?new Date(q.price_as_of).toLocaleTimeString():'just now'}</>:<>{q.stale?'Cached · refresh failed. ':''}{q.price_as_of?`Price time: ${new Date(q.price_as_of).toLocaleString()}`:q.bar_date?`Daily bar: ${q.bar_date}`:'No quote available'}</>}</p></article>})}</div>{data&&<p className="rd-news-note">{data.note} Last checked {new Date(data.checked_at).toLocaleString()}.</p>}</section>
}
