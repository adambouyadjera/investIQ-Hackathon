type Position = { qty: number; entry: number; stop: number; target: number };
type BotPaper = { enabled: boolean; status: string; cash: number; position: Position | null; last_checked_at: string | null; error?: string };

const money = (n: number) => n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Plain-language view of desk/paper.py statuses.
function describe(p: BotPaper, passed: number) {
  if (p.status === 'risk_stopped') return { tone: 'stop', label: 'Stopped for safety', title: 'Stopped for safety', text: 'The practice account fell too far, so the bot locked itself to prevent more losses. It needs a review before it can restart.' };
  if (p.error || p.status === 'data_unavailable') return { tone: 'warn', label: 'Can’t get prices', title: 'Waiting for price data', text: 'The bot couldn’t get reliable Bitcoin prices, so it didn’t buy anything. It will try again automatically.' };
  if (p.position) return { tone: 'on', label: p.enabled ? 'On · owns Bitcoin' : 'Off · owns Bitcoin', title: 'Holding Bitcoin', text: 'The bot will sell automatically if the price falls to its loss limit or rises to its profit target.' };
  if (!p.enabled) return { tone: 'off', label: 'Off', title: 'Bot is off', text: passed ? 'Turn it on to let it trade with practice money.' : 'Turn it on to let it watch the market. It won’t buy until a strategy passes our tests.' };
  if (passed === 0 || p.status === 'waiting_for_validation') return { tone: 'on', label: 'On', title: 'Watching, not buying', text: 'None of the strategies we tested were good enough, so your practice money stays in cash.' };
  return { tone: 'on', label: 'On', title: 'Watching for a good time to buy', text: 'A tested strategy passed. The bot buys only when its rules say so.' };
}

export default function BotStatusPanel({ paper, passed, tested, exposure, busy, onControl }: { paper: BotPaper; passed: number; tested: number; exposure: number; busy: boolean; onControl: (action: 'start' | 'pause' | 'close') => void }) {
  const d = describe(paper, passed);
  const locked = paper.status === 'risk_stopped';
  const checked = paper.last_checked_at ? new Date(paper.last_checked_at) : null;
  return <>
    <div className="rd-panel-heading"><h2>Your practice bot</h2><span className="rd-small-badge">Bitcoin</span></div>
    <section className="rd-decision" aria-live="polite">
      <div className={`rd-bot-state ${d.tone}`}><i/>{d.label}</div>
      <h3>{d.title}</h3>
      <p className="rd-thesis" title={paper.error}>{d.text}</p>
      <div className="rd-decision-facts">
        <div><span>Money in Bitcoin</span><strong>{exposure.toFixed(1)}% <small>(max 50%)</small></strong></div>
        <div><span>Cash</span><strong>{money(paper.cash)} USDT</strong></div>
        {paper.position && <>
          <div><span>Bought at</span><strong>{money(paper.position.entry)}</strong></div>
          <div><span>Sells if price falls to</span><strong className="rd-negative">{money(paper.position.stop)}</strong></div>
          <div><span>Sells if price rises to</span><strong className="rd-positive">{money(paper.position.target)}</strong></div>
        </>}
        <div><span>Strategies that passed tests</span><strong>{passed} of {tested}</strong></div>
      </div>
      <div className="rd-decision-buttons">
        <button className={paper.enabled ? 'rd-secondary' : 'rd-primary'} disabled={busy || locked} onClick={() => onControl(paper.enabled ? 'pause' : 'start')}>{busy ? 'Working…' : locked ? 'Locked for safety' : paper.enabled ? 'Turn bot off' : 'Turn bot on'}</button>
      </div>
      {paper.position && <button className="rd-close" disabled={busy} onClick={() => onControl('close')}>Sell my Bitcoin now</button>}
      <p className="rd-decision-foot">{paper.enabled ? 'Turning it off stops new buys. Safety sells still work.' : 'Uses practice money only. Nothing real is bought.'}</p>
    </section>
    <p className="rd-last-check">Last checked the price<br/><strong>{checked ? checked.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + (checked.toDateString() === new Date().toDateString() ? ' today' : ` · ${checked.toLocaleDateString()}`) : 'Not yet'}</strong></p>
  </>;
}
