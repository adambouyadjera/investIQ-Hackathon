import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import type { SimulateFormData, RiskTier } from '../types';
import { Info } from 'lucide-react';

const schema = z.object({
  amount: z.coerce.number().positive('Must be positive'),
  horizon_years: z.coerce.number().min(1).max(50),
  risk: z.enum(['conservative', 'balanced', 'aggressive']),
  monthly_contribution: z.coerce.number().min(0),
  rebalance: z.enum(['never', 'quarterly', 'annual']),
  extra_fee: z.coerce.number().min(0).max(0.05),
  goal: z.coerce.number().optional(),
});

type FormData = z.infer<typeof schema>;

interface Props {
  onSubmit: (data: SimulateFormData) => void;
  loading: boolean;
  initialValues?: Partial<SimulateFormData>;
}

const RISK_OPTIONS: { value: RiskTier; label: string; desc: string; color: string }[] = [
  { value: 'conservative', label: 'Conservative', desc: 'Capital preservation, steady income', color: 'border-blue-600 bg-blue-900/20' },
  { value: 'balanced', label: 'Balanced', desc: 'Moderate growth with stability', color: 'border-indigo-600 bg-indigo-900/20' },
  { value: 'aggressive', label: 'Aggressive', desc: 'Maximum growth, higher risk', color: 'border-purple-600 bg-purple-900/20' },
];

const TOOLTIPS: Record<string, string> = {
  extra_fee: 'Annual advisor or platform fee on top of the ETF expense ratios. 1% = 0.01.',
  rebalance: 'How often to reset weights back to targets. Annual is usually best for taxable accounts.',
  goal: 'Optional target balance to track probability of hitting it.',
};

export function SimulateForm({ onSubmit, loading, initialValues }: Props) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema) as any,
    defaultValues: {
      amount: initialValues?.amount ?? 10000,
      horizon_years: initialValues?.horizon_years ?? 20,
      risk: initialValues?.risk ?? 'balanced',
      monthly_contribution: initialValues?.monthly_contribution ?? 0,
      rebalance: initialValues?.rebalance ?? 'annual',
      extra_fee: initialValues?.extra_fee ?? 0,
    },
  });

  const selectedRisk = watch('risk');

  return (
    <form onSubmit={handleSubmit((d) => onSubmit(d as unknown as SimulateFormData))} className="flex flex-col gap-5">
      {/* Amount + horizon */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input
          label="Initial Investment"
          type="number"
          prefix="$"
          placeholder="10000"
          error={errors.amount?.message}
          {...register('amount')}
        />
        <Input
          label="Time Horizon (years)"
          type="number"
          suffix="yrs"
          placeholder="20"
          min={1}
          max={50}
          error={errors.horizon_years?.message}
          {...register('horizon_years')}
        />
      </div>

      {/* Risk tier */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-gray-300">Risk Tolerance</label>
        <div className="grid grid-cols-3 gap-2">
          {RISK_OPTIONS.map((opt) => (
            <label key={opt.value} className="cursor-pointer">
              <input type="radio" value={opt.value} {...register('risk')} className="sr-only" />
              <div
                className={`rounded-xl border-2 p-3 transition-all text-center
                  ${selectedRisk === opt.value ? opt.color + ' ring-2 ring-indigo-500' : 'border-gray-700 bg-gray-800 hover:border-gray-600'}`}
              >
                <p className="text-sm font-semibold text-gray-100">{opt.label}</p>
                <p className="text-xs text-gray-400 mt-0.5 hidden sm:block">{opt.desc}</p>
              </div>
            </label>
          ))}
        </div>
        {errors.risk && <p className="text-xs text-red-400">{errors.risk.message}</p>}
      </div>

      {/* Monthly contribution + goal */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input
          label="Monthly Contribution"
          type="number"
          prefix="$"
          placeholder="500"
          hint="Additional money added each month"
          error={errors.monthly_contribution?.message}
          {...register('monthly_contribution')}
        />
        <Input
          label="Goal Amount (optional)"
          type="number"
          prefix="$"
          placeholder="500000"
          hint={TOOLTIPS.goal}
          error={errors.goal?.message}
          {...register('goal')}
        />
      </div>

      {/* Rebalance + fee */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-300 flex items-center gap-1">
            Rebalancing
            <span title={TOOLTIPS.rebalance} className="text-gray-500 cursor-help">
              <Info className="w-3.5 h-3.5" />
            </span>
          </label>
          <select
            {...register('rebalance')}
            className="rounded-lg border border-gray-700 bg-gray-800 text-gray-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="never">Never</option>
            <option value="quarterly">Quarterly</option>
            <option value="annual">Annual</option>
          </select>
        </div>
        <Input
          label="Extra Annual Fee"
          type="number"
          suffix="%/yr"
          placeholder="0"
          step="0.001"
          hint={TOOLTIPS.extra_fee}
          error={errors.extra_fee?.message}
          {...register('extra_fee')}
        />
      </div>

      <Button type="submit" size="lg" loading={loading} className="w-full mt-1">
        Run Simulation
      </Button>
    </form>
  );
}
