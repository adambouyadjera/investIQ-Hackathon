import { Link } from 'react-router-dom';
import { GuestDemoButton } from '../components/GuestDemoButton';
import { TrendingUp, Shield, BarChart2, Zap, ArrowRight } from 'lucide-react';

const features = [
  {
    icon: BarChart2,
    title: 'Real backtests',
    desc: '12+ years of historical price data. See exactly how your portfolio would have performed.',
  },
  {
    icon: Zap,
    title: 'Monte Carlo projections',
    desc: '2,000 simulated futures using block bootstrap resampling — not naive normal assumptions.',
  },
  {
    icon: Shield,
    title: 'Risk-adjusted metrics',
    desc: 'Sharpe, Sortino, Calmar, VaR, max drawdown — the numbers that actually matter.',
  },
  {
    icon: TrendingUp,
    title: 'Strategy comparison',
    desc: 'Conservative vs balanced vs aggressive — see the real trade-offs side by side.',
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Navbar */}
      <nav className="border-b border-gray-800 px-6 h-14 flex items-center justify-between max-w-7xl mx-auto">
        <div className="flex items-center gap-2 font-bold text-lg">
          <TrendingUp className="w-5 h-5 text-indigo-400" />
          InvestIQ
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="text-sm text-gray-400 hover:text-gray-200 transition-colors">
            Log in
          </Link>
          <Link
            to="/register"
            className="text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-1.5 rounded-lg transition-colors"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <div className="max-w-4xl mx-auto px-6 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-900/30 border border-indigo-700 rounded-full px-4 py-1.5 text-sm text-indigo-300 mb-6">
          <Zap className="w-3.5 h-3.5" />
          Real market data · Updated every 5 minutes
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight mb-5">
          See exactly how your{' '}
          <span className="text-indigo-400">investment strategy</span>{' '}
          would have played out
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-8">
          Input your amount, time horizon, and risk tolerance. InvestIQ runs a real historical
          backtest and Monte Carlo projection — no guesswork, no sales pitch.
        </p>
        <div className="flex items-center justify-center gap-4 flex-wrap">
          <Link
            to="/register"
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-xl font-medium transition-colors"
          >
            Start for free
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            to="/login"
            className="px-6 py-3 rounded-xl border border-gray-700 text-gray-300 hover:text-white hover:border-gray-600 font-medium transition-colors"
          >
            Log in
          </Link>
        </div>
        <GuestDemoButton className="mt-6 max-w-xs mx-auto" />
      </div>

      {/* Features */}
      <div className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {features.map((f) => (
            <div key={f.title} className="bg-gray-800 rounded-xl border border-gray-700 p-5">
              <f.icon className="w-5 h-5 text-indigo-400 mb-3" />
              <h3 className="text-sm font-semibold text-white mb-1">{f.title}</h3>
              <p className="text-xs text-gray-400 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>

        {/* Disclaimer */}
        <p className="text-xs text-gray-600 text-center mt-10">
          InvestIQ is for educational purposes only. Past performance does not guarantee future
          results. This is not financial advice. US residents only.
        </p>
      </div>
    </div>
  );
}
