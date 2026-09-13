import { useState } from 'react';

// Official website of each company or fund issuer; the logo is that site's icon.
const DOMAINS: Record<string, string> = {
  SPY: 'ssga.com', QQQ: 'invesco.com', VTI: 'vanguard.com', VXUS: 'vanguard.com', BND: 'vanguard.com', IWM: 'ishares.com', TLT: 'ishares.com',
  XLV: 'sectorspdrs.com', XLF: 'sectorspdrs.com', XLE: 'sectorspdrs.com', GLD: 'spdrgoldshares.com',
  AAPL: 'apple.com', MSFT: 'microsoft.com', NVDA: 'nvidia.com', AMZN: 'amazon.com', GOOGL: 'google.com', JPM: 'jpmorganchase.com',
  JNJ: 'jnj.com', KO: 'coca-colacompany.com', PG: 'pg.com', 'BTC-USD': 'bitcoin.org', 'ETH-USD': 'ethereum.org',
};
const COLORS = ['#53a986', '#6a90cb', '#dbad53', '#c77dba', '#e79486', '#7fc4c9', '#a3b86c', '#d98c4f'];
const color = (ticker: string) => COLORS[[...ticker].reduce((s, c) => s + c.charCodeAt(0), 0) % COLORS.length];

export default function AssetLogo({ ticker, size = 30 }: { ticker: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const domain = DOMAINS[ticker];
  const style = { width: size, height: size, borderRadius: Math.round(size / 4) };
  if (!domain || failed) {
    return <span className="rd-badge" style={{ ...style, background: color(ticker), fontSize: Math.round(size * 0.42) }} aria-hidden="true">{ticker[0]}</span>;
  }
  return <span className="rd-logo" style={style} aria-hidden="true">
    <img src={`https://www.google.com/s2/favicons?domain=${domain}&sz=128`} alt="" loading="lazy" referrerPolicy="no-referrer"
      width={Math.round(size * 0.7)} height={Math.round(size * 0.7)} onError={() => setFailed(true)}/>
  </span>;
}
