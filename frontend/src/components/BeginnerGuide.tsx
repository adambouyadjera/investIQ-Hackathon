import { ArrowRight, Bot, Newspaper, PieChart, type LucideIcon } from 'lucide-react';

const STEPS: { icon: LucideIcon; title: string; text: string; cta: string; to: string }[] = [
  { icon: Bot, title: 'Build Your Investment Plan', text: 'Enter your investment amount, timeline and risk level.', cta: 'Start with Investor AI', to: 'investor-ai' },
  { icon: PieChart, title: 'Explore Stock Recommendations', text: 'See AI-picked stocks and how much to put in each, based on your profile.', cta: 'View Recommendations', to: 'recommendations' },
  { icon: Newspaper, title: 'Stay Informed', text: 'Follow market news and prices that can affect your investments.', cta: 'View Market News', to: 'news' },
];

export default function BeginnerGuide({ onGo }: { onGo: (page: string) => void }) {
  return <ol className="rd-steps" aria-label="Get started in 3 steps">
    {STEPS.map((s, i) => <li key={s.to} className="rd-step-card">
      <div className="rd-step-top"><span className="rd-step-num">{i + 1}</span><s.icon size={22} aria-hidden="true"/></div>
      <h2>{s.title}</h2>
      <p>{s.text}</p>
      <button className="rd-primary rd-step-cta" onClick={() => onGo(s.to)}>{s.cta} <ArrowRight size={16} aria-hidden="true"/></button>
    </li>)}
  </ol>;
}
