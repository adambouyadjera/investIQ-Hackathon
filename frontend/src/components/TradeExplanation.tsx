import { useEffect, useRef } from 'react';
import AssetLogo from './AssetLogo';
import { type PTrade, usd, shares, dateTime } from './portfolioTypes';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section><h4>{title}</h4>{children}</section>;
}

export default function TradeExplanation({ trade, onClose }: { trade: PTrade; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; };
  }, [onClose]);
  const e = trade.explanation, buy = trade.action === 'BUY';
  return <div className="rd-modal-backdrop" onClick={onClose}>
    <div className="rd-modal" role="dialog" aria-modal="true" aria-labelledby="why-title" onClick={ev => ev.stopPropagation()}>
      <header>
        <div className="rd-why-head">
          <AssetLogo ticker={trade.ticker} size={40}/>
          <div>
          <h3 id="why-title">Why This Trade?</h3>
          <p><span className="rd-sim-chip">{buy ? 'Buy' : 'Sell'}</span> {shares(trade.shares)} {trade.ticker} ({trade.name}) at {usd(trade.price)} · {dateTime(trade.time)}</p>
          </div>
        </div>
        <button ref={closeRef} className="rd-modal-close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="rd-modal-body">
        <p className="rd-why-summary">{e.summary}</p>
        <Section title="Market conditions"><p>{e.market}</p><p className="rd-why-note">{e.price_note}</p></Section>
        <Section title="Relevant news">
          {e.news.length > 0 && <ul className="rd-why-news">{e.news.map(n => <li key={n.url}>
            <a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a>
            <span>{n.source}{n.published_at ? ` · ${dateTime(n.published_at)}` : ''}</span>
          </li>)}</ul>}
          <p className="rd-why-note">{e.news_note}</p>
        </Section>
        <Section title="Price trends"><p>{e.price_movement}</p></Section>
        <Section title="Technical indicators"><p>{e.indicators}</p><p>{e.volatility}</p></Section>
        <Section title="Company fundamentals"><p>{e.fundamentals}</p></Section>
        <Section title="Risk factors"><ul>{e.risk_factors.map(r => <li key={r}>{r}</li>)}</ul><p>{e.downside}</p></Section>
        <Section title={buy ? 'Why the AI chose it' : 'How it compared'}>
          <p>{e.why_asset}</p>
          <ul className="rd-why-alts">{e.alternatives.map(a => <li key={a.ticker}><strong>{a.ticker}</strong> {a.name} · score {a.score.toFixed(2)} · <em>{a.status}</em><span>{a.reason}</span></li>)}</ul>
        </Section>
        <Section title="Why this amount"><p>{e.why_amount}</p></Section>
        <Section title="Expected holding period"><p>{e.holding_period}</p></Section>
        <Section title="When the bot would sell"><ul>{e.sell_conditions.map(c => <li key={c}>{c}</li>)}</ul></Section>
        <Section title="What would change the strategy"><ul>{e.strategy_change.map(c => <li key={c}>{c}</li>)}</ul></Section>
        <p className="rd-why-disclaimer">{e.disclaimer}</p>
      </div>
    </div>
  </div>;
}
