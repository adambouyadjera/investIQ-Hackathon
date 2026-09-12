import { ArrowRight, BarChart3, Bot, ChevronDown, Lightbulb } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ResearchDetail, { type ResearchSummary } from './ResearchDetail';

export type HomeTab = 'guide' | 'detail' | null;

export default function BeginnerGuide({ paperEnabled, research, tab, onTab }: { paperEnabled: boolean; research: ResearchSummary; tab: HomeTab; onTab: (tab: HomeTab) => void }) {
  const navigate = useNavigate();
  const tabButton = (key: Exclude<HomeTab, null>, label: string) =>
    <button onClick={() => onTab(tab === key ? null : key)} aria-expanded={tab === key} aria-controls={`home-${key}`}>{label} <ChevronDown size={16} className="rd-beginner-chevron" aria-hidden="true"/></button>;
  return <section className="rd-beginner" aria-label="Guide and details">
    <div className="rd-home-tabs">{tabButton('guide', 'New here? 3-step guide')}{tabButton('detail', 'More detail')}</div>
    <div id="home-guide" className="rd-beginner-body" hidden={tab !== 'guide'}>
      <div className="rd-beginner-grid">
        <button onClick={() => navigate('/?view=markets')}><span className="rd-step">1</span><Lightbulb size={18}/><strong>See prices and news</strong><span>See what markets are doing today.</span><em>See markets <ArrowRight size={14}/></em></button>
        <button onClick={() => navigate('/?view=autopilot')}><span className="rd-step">2</span><BarChart3 size={18}/><strong>Choose your plan</strong><span>Pick a virtual amount, risk level, and timeframe.</span><em>Choose settings <ArrowRight size={14}/></em></button>
        <button onClick={() => navigate('/?view=autopilot')}><span className="rd-step">3</span><Bot size={18}/><strong>{paperEnabled ? 'Your bot is watching' : 'Start your simulation'}</strong><span>{paperEnabled ? 'It watches the market with virtual money.' : 'It will only simulate a trade after safety checks pass.'}</span><em>{paperEnabled ? 'See bot status' : 'Open Bot'} <ArrowRight size={14}/></em></button>
      </div>
      <p className="rd-beginner-note">This app is for learning. The bot uses virtual money and cannot place real orders.</p>
    </div>
    <div id="home-detail" className="rd-beginner-body" hidden={tab !== 'detail'}><ResearchDetail research={research}/></div>
  </section>;
}
