import { useState } from 'react';
import { ExternalLink, ShieldCheck } from 'lucide-react';

const STORAGE_KEY = 'rd-real-checklist';
const ITEMS = [
  ['practice', 'I have practiced with fake money first'],
  ['emergency', 'I have 3–6 months of expenses saved for emergencies'],
  ['debt', 'I have no high-interest debt, like credit card balances'],
  ['time', 'I will only invest money I won’t need for at least 5 years'],
  ['loss', 'I understand I could lose some or all of the money'],
] as const;

export default function RealMoneyGuide({ onPractice }: { onPractice: () => void }) {
  const [done, setDone] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}'); } catch { return {}; }
  });
  const toggle = (key: string) => setDone(d => { const next = { ...d, [key]: !d[key] }; localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); return next; });
  const count = ITEMS.filter(([key]) => done[key]).length;
  return <section className="rd-detail rd-real" aria-labelledby="real-heading">
    <p className="rd-eyebrow">Real money</p>
    <h2 id="real-heading">Before you invest real money</h2>
    <p className="rd-real-banner"><ShieldCheck size={16} aria-hidden="true"/> InvestIQ never holds or trades your money. You buy and sell yourself, at a regulated broker.</p>

    <h3>Are you ready? <small>{count} of {ITEMS.length} done</small></h3>
    <ul className="rd-checklist">{ITEMS.map(([key, label]) => <li key={key}>
      <label><input type="checkbox" checked={!!done[key]} onChange={() => toggle(key)}/>{label}</label>
      {key === 'practice' && !done[key] && <button onClick={onPractice}>Try fake money</button>}
    </li>)}</ul>
    <p className={count === ITEMS.length ? 'rd-real-ready' : 'rd-news-note'}>{count === ITEMS.length ? 'You’re ready to look at brokers. Start small.' : 'Finish the checklist before investing. There’s no rush.'}</p>

    <h3>Choose a regulated broker</h3>
    <p>Only use a broker registered with your country’s regulator. In the US you can look any broker up for free:</p>
    <div className="rd-real-links">
      <a href="https://brokercheck.finra.org/" target="_blank" rel="noopener noreferrer">FINRA BrokerCheck <ExternalLink size={13} aria-hidden="true"/></a>
      <a href="https://www.investor.gov/" target="_blank" rel="noopener noreferrer">Investor.gov (SEC) <ExternalLink size={13} aria-hidden="true"/></a>
    </div>

    <h3>Beginner basics</h3>
    <ul className="rd-real-basics">
      <li>Start with a small amount while you learn.</li>
      <li>Spreading money across many companies lowers the risk of any one of them failing.</li>
      <li>Check the fees — small yearly fees add up over time.</li>
      <li>Bitcoin’s price has fallen by more than half several times. Only use money you can afford to lose.</li>
      <li>Be wary of anyone promising guaranteed or fast returns.</li>
    </ul>
    <p className="rd-news-note">Educational information only, not financial advice.</p>
  </section>;
}
