"""Publisher RSS headlines for local research; never trading instructions."""
import concurrent.futures
import html
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from .paper import ROOT, locked, atomic_json

SOURCES = [
    {'name':'BBC News','url':'https://feeds.bbci.co.uk/news/business/rss.xml','domains':['bbc.com','bbc.co.uk']},
    {'name':'The Guardian','url':'https://www.theguardian.com/business/rss','domains':['theguardian.com']},
    {'name':'CoinDesk','url':'https://www.coindesk.com/arc/outboundfeeds/rss/','domains':['coindesk.com']},
    {'name':'CNBC','url':'https://www.cnbc.com/id/100003114/device/rss/rss.html','domains':['cnbc.com']},
    {'name':'Yahoo Finance','url':'https://finance.yahoo.com/news/rssindex','domains':['yahoo.com']},
]
TTL = 600
CACHE = ROOT/'state/news-cache.json'

def parse_feed(payload, source):
    if len(payload)>2_000_000 or b'<!ENTITY' in payload.upper() or b'<!DOCTYPE' in payload.upper():
        raise ValueError('Unsafe or oversized feed')
    root=ET.fromstring(payload)
    if root.tag!='rss':raise ValueError('Unsupported feed format')
    items=[]
    for node in root.findall('./channel/item')[:100]:
        title=html.unescape(re.sub('<[^>]*>','',node.findtext('title') or '')).strip()[:300]
        link=(node.findtext('link') or '').strip();url=urlsplit(link)
        if not title or url.scheme not in ['http','https'] or url.username or not any((url.hostname or '')==d or (url.hostname or '').endswith('.'+d) for d in source['domains']):continue
        try:
            dt=parsedate_to_datetime(node.findtext('pubDate') or '')
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            published=dt.astimezone(timezone.utc).isoformat()
        except (ValueError,TypeError,OverflowError):published=None
        if published and dt.timestamp()>time.time()+600:continue
        topic='Crypto' if re.search(r'\b(bitcoin|btc|crypto\w*|ethereum|ether|stablecoins?|blockchain|tokeniz\w*)\b',title,re.I) else ('Economy' if re.search(r'\b(inflation|fed|federal reserve|interest rates?|central bank|tariffs?|treasury|dollar|recession)\b',title,re.I) else 'Business')
        items.append({'title':title,'url':link,'source':source['name'],'published_at':published,'topic':topic})
    return items

def fetch(source):
    try:
        r=subprocess.run(['curl','--fail','--silent','--show-error','--location','--proto','=https','--proto-redir','=https','--max-time','12','--max-filesize','2000000',source['url']],capture_output=True,timeout=15,check=True)
        return {'name':source['name'],'feed_url':source['url'],'status':'ok','items':parse_feed(r.stdout,source)}
    except (subprocess.SubprocessError,OSError,ValueError,ET.ParseError):
        return {'name':source['name'],'feed_url':source['url'],'status':'unavailable','items':[]}

def get_news():
    with locked(ROOT/'state/news.lock'):
        try:previous=json.loads(CACHE.read_text())
        except (OSError,ValueError):previous={}
        if time.time()-previous.get('checked_epoch',0)<TTL:return previous
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(fetch,SOURCES))
        now=datetime.now(timezone.utc).isoformat();items=[];sources=[]
        for result in results:
            fresh=result.pop('items')
            old=next((s for s in previous.get('sources',[]) if s['name']==result['name']),{})
            result['last_success_at']=now if result['status']=='ok' else old.get('last_success_at')
            if result['status']!='ok':
                fresh=[dict(x,stale=True) for x in previous.get('items',[]) if x['source']==result['name']]
            else:fresh=[dict(x,stale=False) for x in fresh]
            sources.append(result);items.extend(fresh)
        seen=set();dedup=[]
        for x in sorted(items,key=lambda x:x['published_at'] or '',reverse=True):
            key=(x['source'],x['title'].casefold())
            if key not in seen:seen.add(key);dedup.append(x)
        report={'checked_epoch':time.time(),'checked_at':now,'refresh_minutes':10,'sources':sources,'items':dedup[:120],
                'purpose':'Publisher headlines for research context. Not a trading signal.'}
        atomic_json(CACHE,report);return report
if __name__=='__main__':
    r=get_news();print(json.dumps({'sources':r['sources'],'headlines':len(r['items'])}))
