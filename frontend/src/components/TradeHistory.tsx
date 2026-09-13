import AssetLogo from './AssetLogo';
import { type ConfiguredPortfolio, type PTrade, usd, shares, dateTime, signedUsd, tone } from './portfolioTypes';

function Pnl({ t }: { t: PTrade }) {
  if (t.pnl == null) return <span className="rd-pnl-muted">Sold later</span>;
  return <span className={tone(t.pnl)}>{signedUsd(t.pnl)}<small>{t.pnl_type}</small></span>;
}

export default function TradeHistory({ data, onWhy }: { data: ConfiguredPortfolio; onWhy: (t: PTrade) => void }) {
  const trades = [...data.trades].reverse();
  const activity = [...data.activity].reverse();
  return <>
    <section className="rd-phistory" aria-labelledby="history-heading">
      <div className="rd-phistory-head"><h3 id="history-heading">Trades</h3><span>{trades.length} total · newest first</span></div>
      {!trades.length ? <p className="rd-trades-empty">No trades yet.</p> :
        <div className="rd-table-scroll"><table className="rd-ptable">
          <thead><tr>
            <th>Date &amp; time</th><th>Company</th><th>Ticker</th><th>Action</th><th>Shares / units</th><th>Price</th><th>Trade value</th>
            <th>Cash after</th><th>Portfolio value</th><th>Profit / loss</th><th><span className="rd-sr-only">Explanation</span></th>
          </tr></thead>
          <tbody>{trades.map(t => <tr key={t.id}>
            <td>{dateTime(t.time)}</td><td><span className="rd-sym"><AssetLogo ticker={t.ticker} size={24}/>{t.name}</span></td><td className="rd-mono">{t.ticker}</td>
            <td><span className={`rd-action ${t.action === 'BUY' ? 'buy' : 'sell'}`}>{t.action === 'BUY' ? 'Buy' : 'Sell'}{t.replayed ? ' · replay' : ''}</span></td>
            <td>{shares(t.shares)}</td><td>{usd(t.price)}</td><td>{usd(t.value)}</td><td>{usd(t.cash_after)}</td><td>{usd(t.portfolio_after)}</td>
            <td className="rd-pnl-cell"><Pnl t={t}/></td>
            <td><button className="rd-why-btn" onClick={() => onWhy(t)}>Why This Trade?</button></td>
          </tr>)}</tbody>
        </table></div>}
    </section>
    <section className="rd-pcard" aria-labelledby="activity-heading">
      <h3 id="activity-heading">Bot activity</h3>
      <ul className="rd-activity-log">{activity.map((a, i) => <li key={a.time + i}><time>{dateTime(a.time)}</time>{a.text}</li>)}</ul>
    </section>
  </>;
}
