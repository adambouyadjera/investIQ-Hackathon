import { useEffect, useState } from 'react';
import { ExternalLink, Newspaper } from 'lucide-react';
import api from '../api/client';
type Item={title:string;url:string;source:string;published_at:string|null;topic:string;stale:boolean};
type Feed={checked_at:string;sources:{name:string;status:string;last_success_at:string|null}[];items:Item[]};
export default function DeskNews({compact=false}:{compact?:boolean}){
 const [feed,setFeed]=useState<Feed|null>(null),[error,setError]=useState(''),[source,setSource]=useState('All'),[topic,setTopic]=useState('All');
 async function load(){try{setFeed((await api.get<Feed>('/research/news')).data);setError('');}catch{setError('News could not be refreshed. Try again shortly.');}}
 useEffect(()=>{void load();const timer=setInterval(()=>void load(),600000);return()=>clearInterval(timer);},[]);
 const rows=feed?.items.filter(x=>(source==='All'||x.source===source)&&(topic==='All'||x.topic===topic)).slice(0,compact?4:30)??[];
 return <section className="rd-news"><div className="rd-news-heading"><h2><Newspaper size={16}/> Market news</h2><span>Publisher feeds · every 10 min</span></div><p className="rd-news-note">Headlines for context, not automatic trading signals.</p>
 {!compact&&<div className="rd-news-filters"><label>Source<select aria-label="News source" value={source} onChange={e=>setSource(e.target.value)}><option>All</option>{feed?.sources.map(s=><option key={s.name}>{s.name}</option>)}</select></label><label>Topic<select aria-label="News topic" value={topic} onChange={e=>setTopic(e.target.value)}>{['All','Crypto','Economy','Business'].map(t=><option key={t}>{t}</option>)}</select></label></div>}
 {error&&<p role="alert" className="rd-feed-error">{error} <button onClick={()=>void load()}>Retry</button></p>}
 {!feed&&!error&&<p className="rd-news-note" role="status">Loading publisher headlines…</p>}
 <div>{rows.map(x=><article key={x.url+x.source}><div className="rd-news-meta"><strong>{x.source}</strong><span>{x.topic}</span><time dateTime={x.published_at??undefined}>{x.published_at?new Date(x.published_at).toLocaleString():'Publication time unavailable'}</time>{x.stale&&<span className="rd-amber">Cached · feed unavailable</span>}</div><a href={x.url} target="_blank" rel="noopener noreferrer">{x.title}<ExternalLink size={12}/></a></article>)}</div>
 {feed&&!rows.length&&<p className="rd-news-note">No headlines available for this selection.</p>}
 {feed&&<div className="rd-news-status">{feed.sources.map(s=><span key={s.name} className={s.status==='ok'?'':'rd-amber'}>{s.name}: {s.status==='ok'?'connected':'unavailable'}</span>)}<p>Checked {new Date(feed.checked_at).toLocaleString()}. Publication times above come from each publisher. Headlines can be older than the latest feed check.</p></div>}
 </section>
}
