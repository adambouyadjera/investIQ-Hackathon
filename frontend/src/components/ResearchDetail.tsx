export type ResearchSummary = {
  configurations_tested: number;
  validated_candidates: number;
  passed_candidates: number;
  validations: { key: string; name: string; metrics: { net_return: number }; gates: Record<string, boolean> }[];
};

// [gate key, what passing means, short reason when it fails]
const CHECKS: [string, string, string][] = [
  ['positive_return', 'Made money overall', 'Lost money'],
  ['profit_factor_at_least_1_10', 'Earned at least $1.10 for every $1 lost', 'Wins too small vs. losses'],
  ['sufficient_trades', 'Made enough trades to trust the result', 'Too few trades'],
  ['drawdown_below_10pct', 'Never fell more than 10% from its high', 'Fell too far'],
  ['no_risk_stop', 'Never hit the emergency stop', 'Hit the emergency stop'],
  ['positive_under_double_costs', 'Still made money with double fees', 'Lost money with higher fees'],
  ['majority_positive_quarters', 'Made money in most 3-month periods', 'Lost money most quarters'],
];

export default function ResearchDetail({ research }: { research: ResearchSummary }) {
  const rows = [...research.validations].sort((a, b) => b.metrics.net_return - a.metrics.net_return);
  const passed = research.passed_candidates;
  return <div className="rd-home-detail">
    <h3>How the bot was tested</h3>
    <ol className="rd-funnel">
      <li><strong>{research.configurations_tested}</strong><span>strategies tried on past Bitcoin prices</span></li>
      <li><strong>{research.validated_candidates}</strong><span>best ones re-tested on Jan 2025 – Mar 2026, with fees included</span></li>
      <li><strong className={passed ? 'rd-positive' : 'rd-amber'}>{passed}</strong><span>passed every safety check</span></li>
    </ol>
    <p className="rd-detail-sum">{passed === 0 ? 'None were good enough yet, so the bot waits in cash instead of risking money.' : `${passed} ${passed === 1 ? 'strategy' : 'strategies'} passed every check.`} Prices from April 2026 onward are kept unused, for one final check once a strategy passes.</p>

    <h3>The {CHECKS.length} checks a strategy must pass</h3>
    <ul className="rd-check-list">{CHECKS.map(([key, label]) => <li key={key}>{label}</li>)}</ul>

    <h3>Results</h3>
    <div className="rd-table-scroll"><table className="rd-detail-table">
      <thead><tr><th>Strategy</th><th>Result</th><th>Checks passed</th><th>Main reason</th></tr></thead>
      <tbody>{rows.map(x => {
        const failed = CHECKS.filter(([key]) => x.gates[key] === false);
        const r = x.metrics.net_return * 100;
        return <tr key={x.key}>
          <td>{x.name}</td>
          <td className={r < 0 ? 'rd-negative' : 'rd-positive'}>{r >= 0 ? '+' : ''}{r.toFixed(1)}%</td>
          <td>{CHECKS.length - failed.length} of {CHECKS.length}</td>
          <td>{failed.length ? failed.slice(0, 2).map(f => f[2]).join(' · ') : 'Passed'}</td>
        </tr>;
      })}</tbody>
    </table></div>
    <p className="rd-news-note">Past results don’t predict future returns. Research re-runs hourly on this computer using free public data.</p>
  </div>;
}
