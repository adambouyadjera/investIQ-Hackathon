import unittest,tempfile,json,time
from pathlib import Path
from unittest.mock import patch
from desk import news

class NewsTests(unittest.TestCase):
    def test_safe_headlines_and_links(self):
        xml=b'<rss><channel><item><title>Bitcoin &amp; rates</title><link>https://bbc.com/news/a</link><pubDate>Sat, 12 Sep 2026 12:00:00 GMT</pubDate></item><item><title>Bad</title><link>javascript:alert(1)</link></item><item><title>Fake</title><link>https://bbc.com.evil.org/a</link></item></channel></rss>'
        rows=news.parse_feed(xml,news.SOURCES[0]);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['topic'],'Crypto');self.assertEqual(rows[0]['title'],'Bitcoin & rates')
    def test_entities_rejected(self):
        with self.assertRaises(ValueError):news.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "abc">]><rss/>',news.SOURCES[0])
    def test_ttl_avoids_repeat_fetches(self):
        with tempfile.TemporaryDirectory() as d,patch.object(news,'ROOT',Path(d)),patch.object(news,'CACHE',Path(d)/'cache.json'),patch.object(news,'fetch') as fetch:
            news.CACHE.write_text(json.dumps({'checked_epoch':time.time(),'items':[]}))
            news.get_news();fetch.assert_not_called()
    def test_failure_marks_cached_items_stale(self):
        with tempfile.TemporaryDirectory() as d,patch.object(news,'ROOT',Path(d)),patch.object(news,'CACHE',Path(d)/'cache.json'),patch.object(news,'fetch',side_effect=lambda s:{'name':s['name'],'status':'unavailable','items':[]}):
            news.CACHE.write_text(json.dumps({'checked_epoch':0,'sources':[],'items':[{'source':'BBC News','title':'Prior headline','url':'https://bbc.com/news/a','published_at':None,'stale':False}]}))
            r=news.get_news();self.assertTrue(r['items'][0]['stale']);self.assertEqual(r['sources'][0]['status'],'unavailable')
