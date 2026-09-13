import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { logout } from '../store/auth';
import { ArrowRight, Bot, Info, LayoutGrid, LogOut, Newspaper, PieChart, TrendingUp } from 'lucide-react';
import BeginnerGuide from '../components/BeginnerGuide';
import Simulator from '../components/Simulator';
import DeskNews from '../components/DeskNews';
import YahooQuotes from '../components/YahooQuotes';
import PortfolioBot from '../components/PortfolioBot';
import { useBinanceTicker } from '../hooks/useBinanceTicker';
import './research-desk.css';

const money=(n:number)=>n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const NAV=[
 {key:'home',label:'Home',icon:LayoutGrid,sub:''},
 {key:'investor-ai',label:'Investor AI',icon:Bot,sub:'Enter your amount, risk level and timeline. The AI builds a strategy, manages the portfolio and explains every trade.'},
 {key:'recommendations',label:'Stock Recommendations',icon:PieChart,sub:'Stocks and ETFs picked for your risk level and timeline, with how much to put in each.'},
 {key:'news',label:'Market News',icon:Newspaper,sub:'The latest headlines and prices that can move your investments.'},
 {key:'info',label:'Info',icon:Info,sub:'How InvestIQ works and what to know before you invest.'},
];
// Links saved before the redesign still open the right page.
const LEGACY:Record<string,string>={overview:'home',autopilot:'investor-ai',simulator:'recommendations',markets:'news',limits:'info'};
const NEXT:Record<string,string>={'investor-ai':'recommendations',recommendations:'news'};

// Mirrors RISK in desk/portfolio_bot.py.
const RULES:[string,string,string,string][]=[
 ['Cash kept aside','25%','10%','5%'],
 ['Most in one investment','20%','25%','35%'],
 ['Most in company stocks','20%','50%','85%'],
 ['Most in one industry','30%','35%','50%'],
 ['Most in crypto (Bitcoin, Ethereum)','0%','10%','20%'],
 ['Sells an investment after a loss of','8%','12%','18%'],
 ['Skips investments with yearly volatility above','30%','50%','90%'],
 ['Investments held at most','6','5','4'],
];
const FACTORS:[string,string][]=[
 ['Risk tolerance','Sets limits, like how much can go into one stock or industry.'],
 ['Timeline','Short plans follow recent momentum; long plans favor steady trends and strong companies.'],
 ['Amount','Split into exact dollar amounts that add up to what you enter.'],
 ['Market conditions','The overall market trend and how much prices are swinging.'],
 ['Historical performance','Price momentum over 1 to 12 months, trend lines and RSI.'],
 ['Diversification','Caps per investment and industry, with more broad funds at lower risk.'],
 ['News signals','Recent headlines make up about a third of each recommendation score.'],
];
const DATA:[string,string][]=[
 ['Prices','Yahoo Finance, with up to 10 years of history, and live crypto prices from Binance.'],
 ['Company data','Profit margins, revenue growth and price-to-earnings ratios.'],
 ['News','Headlines for each stock from Yahoo Finance, plus BBC, The Guardian and CoinDesk.'],
 ['Updates','Prices refresh every few minutes. Headline tone is judged by keywords, so it can misread a story.'],
];
const TERMS:[string,string][]=[
 ['Stock','A small piece of one company.'],
 ['ETF','A fund that holds many stocks or bonds at once.'],
 ['Portfolio','Everything you own: investments plus cash.'],
 ['Diversification','Spreading money across many investments to lower risk.'],
 ['Volatility','How much a price swings up and down.'],
 ['Profit / loss','How much more or less your investments are worth than what you put in.'],
];

function NewsPage(){
 const live=useBinanceTicker('btcusdt'), t=live.ticker;
 return <div className="rd-news-layout">
  <div className="rd-news-main"><DeskNews/></div>
  <aside className="rd-news-side" aria-label="Prices">
   <section className="rd-card rd-btc" aria-label="Bitcoin live price">
    <div className="rd-news-meta"><strong>BTC/USDT</strong><span>Binance</span><span className="rd-live-inline"><span className={`rd-live-dot${live.status==='live'?'':' off'}`} aria-hidden="true"/>{live.status==='live'?'Live':live.status==='connecting'?'Connecting…':'Reconnecting…'}</span></div>
    <div className="rd-yahoo-price"><a href="https://www.tradingview.com/symbols/BTCUSDT/" target="_blank" rel="noopener noreferrer">{t?money(t.price):'—'}</a>{t&&<span className={t.changePct<0?'rd-negative':'rd-positive'}>{t.changePct>=0?'+':''}{t.changePct.toFixed(2)}% 24h</span>}</div>
   </section>
   <YahooQuotes/>
  </aside>
 </div>;
}

function InfoPage(){
 return <div className="rd-info">
  <div className="rd-info-grid">
   <section className="rd-info-card"><h2>How InvestIQ Works</h2><p>InvestIQ combines what you tell it — amount, timeline and risk level — with live prices, years of price history and the latest news.</p><p>Its AI analyzes that data to recommend investments and manage a portfolio within your limits.</p></section>
   <section className="rd-info-card"><h2>Data &amp; Analysis</h2><ul className="rd-info-list">{DATA.map(([k,v])=><li key={k}><strong>{k}:</strong> {v}</li>)}</ul></section>
  </div>
  <section className="rd-info-card"><h2>How AI Makes Decisions</h2><ul className="rd-info-list rd-info-factors">{FACTORS.map(([k,v])=><li key={k}><strong>{k}</strong><span>{v}</span></li>)}</ul></section>
  <section className="rd-info-card"><h2>Risk Limits by Level</h2><p>Investor AI checks these limits every 5 minutes. Stocks trade during US market hours; crypto trades 24/7.</p>
   <div className="rd-table-scroll"><table className="rd-ptable rd-rules"><thead><tr><th>Rule</th><th>Low</th><th>Medium</th><th>High</th></tr></thead><tbody>{RULES.map(([rule,...v])=><tr key={rule}><td>{rule}</td>{v.map((x,i)=><td key={i}>{x}</td>)}</tr>)}</tbody></table></div>
  </section>
  <div className="rd-info-grid">
   <section className="rd-info-card warn"><h2>Understanding Risk</h2><p>All investing involves risk, and you can lose money. AI recommendations are based on past data and cannot guarantee profit.</p></section>
   <section className="rd-info-card"><h2>Important Disclaimer</h2><p>InvestIQ provides educational and analytical insights, not financial advice. Investor AI runs a practice portfolio and never places real orders. Always make your own financial decisions.</p></section>
  </div>
  <section className="rd-info-card"><h2>Words to Know</h2><div className="rd-glossary"><dl>{TERMS.map(([k,v])=><div key={k} className="rd-term"><dt>{k}</dt><dd>{v}</dd></div>)}</dl></div></section>
 </div>;
}

export default function ResearchDeskPage(){
 const [params,setParams]=useSearchParams();
 const redirect=useNavigate();
 const raw=params.get('view')??'home';
 const page=NAV.find(n=>n.key===(LEGACY[raw]??raw))??NAV[0];
 const go=(key:string)=>{setParams(key==='home'?{}:{view:key});window.scrollTo({top:0});};
 const next=NAV.find(n=>n.key===NEXT[page.key]);
 return <div className="research-desk">
  <aside className="rd-sidebar">
   <Link to="/" className="rd-brand"><TrendingUp size={21}/>InvestIQ<span>LAB</span></Link>
   <nav aria-label="Main">{NAV.map(n=><button key={n.key} aria-label={n.label} title={n.label} aria-current={page.key===n.key?'page':undefined} onClick={()=>go(n.key)} className={page.key===n.key?'active':''}><n.icon size={18}/><span>{n.label}</span></button>)}</nav>
   <button className="rd-signout" onClick={()=>{logout();redirect('/login');}} aria-label="Sign out" title="Sign out"><LogOut size={18}/><span>Sign out</span></button>
  </aside>
  <div className="rd-workspace">
   <main className="rd-main">
    {page.key==='home'?<>
     <div className="rd-hero"><h1>Welcome to InvestIQ</h1><p>Make smarter investing decisions with AI, market data and recommendations built around you.</p></div>
     <p className="rd-eyebrow">Get started in 3 steps</p>
     <BeginnerGuide onGo={go}/>
    </>:<div className="rd-page-head"><h1>{page.label}</h1><p>{page.sub}</p></div>}
    {page.key==='investor-ai'&&<PortfolioBot/>}
    {page.key==='recommendations'&&<Simulator/>}
    {page.key==='news'&&<NewsPage/>}
    {page.key==='info'&&<InfoPage/>}
    {next&&<div className="rd-next"><button className="rd-secondary" onClick={()=>go(next.key)}>Next: {next.label} <ArrowRight size={16} aria-hidden="true"/></button></div>}
   </main>
   <footer className="rd-footer"><span>Educational insights, not financial advice. Investing involves risk.</span></footer>
  </div>
 </div>;
}
