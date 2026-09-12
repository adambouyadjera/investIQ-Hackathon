import { useEffect, useState } from 'react';
import { Layout } from '../components/layout/Layout';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { ResultsPanel } from '../components/ResultsPanel';
import { getScenarios, deleteScenario } from '../api/scenarios';
import type { Scenario, RiskTier, SimulationResult } from '../types';
import { Trash2, Eye } from 'lucide-react';

const TIER_BADGE: Record<RiskTier, 'blue' | 'purple' | 'red'> = {
  conservative: 'blue',
  balanced: 'purple',
  aggressive: 'red',
};

function money(n: number) {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<SimulationResult | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    getScenarios()
      .then(setScenarios)
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(id: string) {
    setDeleting(id);
    try {
      await deleteScenario(id);
      setScenarios((prev) => prev.filter((s) => s.id !== id));
      if (viewing) setViewing(null);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <Layout>
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Saved Scenarios</h1>
          <p className="text-gray-400 text-sm mt-1">
            You can save up to 10 simulations to compare later.
          </p>
        </div>

        {loading ? (
          <div className="text-gray-400 text-sm">Loading...</div>
        ) : scenarios.length === 0 ? (
          <div className="bg-gray-800 rounded-xl border border-gray-700 p-10 text-center text-gray-400">
            <p className="text-lg font-medium text-gray-300 mb-1">No saved scenarios yet</p>
            <p className="text-sm">Run a simulation and click "Save" to store it here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {scenarios.map((s) => (
              <div key={s.id} className="bg-gray-800 rounded-xl border border-gray-700 p-4 flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-gray-100 line-clamp-2">{s.name}</p>
                  <Badge color={TIER_BADGE[s.risk_tier]}>{s.risk_tier}</Badge>
                </div>
                <div className="text-xs text-gray-400 flex flex-col gap-1">
                  <span>Amount: {money(s.amount)}</span>
                  <span>Horizon: {s.horizon_years} years</span>
                  {s.monthly_contribution > 0 && (
                    <span>Monthly: {money(s.monthly_contribution)}/mo</span>
                  )}
                  {s.result_json && (
                    <span className="text-emerald-400">
                      Median outcome: {money(s.result_json.projection.final_p50)}
                    </span>
                  )}
                  <span className="text-gray-600">{new Date(s.created_at).toLocaleDateString()}</span>
                </div>
                <div className="flex gap-2 mt-auto">
                  {s.result_json && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setViewing(viewing?.inputs.risk === s.risk_tier ? null : s.result_json!)}
                    >
                      <Eye className="w-3.5 h-3.5" />
                      View
                    </Button>
                  )}
                  <Button
                    variant="danger"
                    size="sm"
                    loading={deleting === s.id}
                    onClick={() => handleDelete(s.id)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Delete
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        {viewing && (
          <div className="mt-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Scenario Details</h2>
              <Button variant="ghost" size="sm" onClick={() => setViewing(null)}>
                Close
              </Button>
            </div>
            <ResultsPanel result={viewing} />
          </div>
        )}
      </div>
    </Layout>
  );
}
