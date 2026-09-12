import { useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { SimulateForm } from '../components/SimulateForm';
import { ResultsPanel } from '../components/ResultsPanel';
import { SavingsAdvisor } from '../components/SavingsAdvisor';
import { RiskQuestionnaire } from '../components/RiskQuestionnaire';
import { Card } from '../components/ui/Card';
import { simulate } from '../api/portfolio';
import type { SimulationResult, SimulateFormData } from '../types';
import { useAuth } from '../hooks/useAuth';
import { ChevronDown, ChevronUp, Calculator, HelpCircle } from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showSavings, setShowSavings] = useState(false);
  const [showQuestionnaire, setShowQuestionnaire] = useState(false);
  const [recommendedRisk, setRecommendedRisk] = useState<string | null>(null);

  async function handleSimulate(data: SimulateFormData) {
    setLoading(true);
    setError('');
    try {
      const res = await simulate(data);
      setResult(res);
      // Scroll to results
      setTimeout(() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' }), 100);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Simulation failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        {/* Welcome */}
        <div>
          <h1 className="text-2xl font-bold text-white">
            Welcome back, {user?.username ?? 'investor'} 👋
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Build and simulate your investment strategy. All projections are based on historical data.
          </p>
        </div>

        {/* Collapsible savings advisor */}
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <button
            onClick={() => setShowSavings(!showSavings)}
            className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-750 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Calculator className="w-4 h-4 text-indigo-400" />
              <span className="text-sm font-medium text-gray-200">
                How much should I be investing? (Income Calculator)
              </span>
            </div>
            {showSavings ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>
          {showSavings && (
            <div className="px-5 pb-5 border-t border-gray-700">
              <SavingsAdvisor />
            </div>
          )}
        </div>

        {/* Collapsible risk questionnaire */}
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <button
            onClick={() => setShowQuestionnaire(!showQuestionnaire)}
            className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-750 transition-colors"
          >
            <div className="flex items-center gap-2">
              <HelpCircle className="w-4 h-4 text-purple-400" />
              <span className="text-sm font-medium text-gray-200">
                Not sure what risk level fits you? Take the questionnaire
              </span>
            </div>
            {showQuestionnaire ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
          </button>
          {showQuestionnaire && (
            <div className="px-5 pb-5 border-t border-gray-700">
              <RiskQuestionnaire
                onResult={(tier) => {
                  setRecommendedRisk(tier);
                  setShowQuestionnaire(false);
                }}
              />
            </div>
          )}
        </div>

        {recommendedRisk && (
          <div className="bg-indigo-900/30 border border-indigo-700 rounded-xl p-4 text-sm text-indigo-200">
            Based on your answers, we recommend the{' '}
            <strong className="text-indigo-100 capitalize">{recommendedRisk}</strong> portfolio.
            Select it in the form below.
          </div>
        )}

        {/* Simulation form */}
        <Card title="Portfolio Simulation" subtitle="Configure your investment parameters">
          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}
          <SimulateForm onSubmit={handleSimulate} loading={loading} />
        </Card>

        {/* Results */}
        {result && (
          <div id="results">
            <ResultsPanel result={result} />
          </div>
        )}
      </div>
    </Layout>
  );
}
