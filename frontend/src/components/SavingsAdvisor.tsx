import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Input } from './ui/Input';
import { Button } from './ui/Button';
import { savingsCapacity } from '../api/portfolio';
import type { SavingsResult } from '../types';
import { AlertTriangle } from 'lucide-react';

const schema = z.object({
  monthly_take_home: z.coerce.number().positive('Enter your monthly take-home pay'),
  monthly_essentials: z.coerce.number().min(0).optional(),
  high_interest_debt: z.coerce.number().min(0),
  emergency_fund: z.coerce.number().min(0),
});

type FormData = z.infer<typeof schema>;

function money(n: number) {
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

export function SavingsAdvisor() {
  const [result, setResult] = useState<SavingsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema) as any,
    defaultValues: { high_interest_debt: 0, emergency_fund: 0 },
  });

  async function onSubmit(data: FormData) {
    setLoading(true);
    try {
      const res = await savingsCapacity({
        monthly_take_home: data.monthly_take_home,
        monthly_essentials: data.monthly_essentials,
        high_interest_debt: data.high_interest_debt ?? 0,
        emergency_fund: data.emergency_fund ?? 0,
      });
      setResult(res);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 pt-4">
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input
            label="Monthly Take-Home Pay"
            type="number"
            prefix="$"
            placeholder="5000"
            error={errors.monthly_take_home?.message}
            {...register('monthly_take_home')}
          />
          <Input
            label="Monthly Essentials (rent, food, etc.)"
            type="number"
            prefix="$"
            placeholder="Auto: 50% of income"
            hint="Leave blank to use the 50/30/20 baseline"
            {...register('monthly_essentials')}
          />
          <Input
            label="High-Interest Debt Balance"
            type="number"
            prefix="$"
            placeholder="0"
            hint="Credit cards, personal loans >7%"
            {...register('high_interest_debt')}
          />
          <Input
            label="Current Emergency Fund"
            type="number"
            prefix="$"
            placeholder="0"
            hint="Liquid savings you can access quickly"
            {...register('emergency_fund')}
          />
        </div>
        <Button type="submit" size="sm" loading={loading} className="w-40">
          Calculate
        </Button>
      </form>

      {result && (
        <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 flex flex-col gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div>
              <p className="text-xs text-gray-400">Take-home</p>
              <p className="text-base font-bold text-gray-100">{money(result.monthly_take_home)}/mo</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Essentials</p>
              <p className="text-base font-bold text-gray-100">{money(result.monthly_essentials)}/mo</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Monthly Surplus</p>
              <p className="text-base font-bold text-emerald-400">{money(result.monthly_surplus)}/mo</p>
            </div>
            <div>
              <p className="text-xs text-gray-400">Recommended Investment</p>
              <p className="text-base font-bold text-indigo-400">{money(result.recommended_monthly_investment)}/mo</p>
              <p className="text-xs text-gray-500">{pct(result.effective_savings_rate)} of income</p>
            </div>
          </div>

          {result.emergency_fund_gap > 0 && (
            <div className="text-xs text-amber-300 bg-amber-900/20 border border-amber-800/50 rounded-lg p-2">
              Emergency fund gap: {money(result.emergency_fund_gap)} · target: {money(result.emergency_fund_target)}
            </div>
          )}

          {result.warnings.map((w, i) => (
            <div key={i} className="flex gap-2 text-xs text-amber-300 bg-amber-900/20 border border-amber-800/50 rounded-lg p-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
