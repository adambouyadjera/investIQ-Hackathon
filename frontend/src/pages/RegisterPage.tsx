import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TrendingUp, ShieldCheck } from 'lucide-react';
import { register as registerUser } from '../api/auth';
import { getMe } from '../api/auth';
import { setUser } from '../store/auth';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';

const schema = z.object({
  email: z.string().email('Enter a valid email'),
  username: z.string().min(3, 'Username must be at least 3 characters'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Must include an uppercase letter')
    .regex(/[0-9]/, 'Must include a number'),
  date_of_birth: z.string().refine((val) => {
    const dob = new Date(val);
    const today = new Date();
    const age = today.getFullYear() - dob.getFullYear();
    const hasBirthdayPassed =
      today.getMonth() > dob.getMonth() ||
      (today.getMonth() === dob.getMonth() && today.getDate() >= dob.getDate());
    return age > 18 || (age === 18 && hasBirthdayPassed);
  }, 'You must be at least 18 years old'),
  monthly_income: z.string().optional(),
  is_us_citizen: z.boolean().refine((v) => v === true, {
    message: 'You must be a US citizen to use this platform',
  }),
  age_confirm: z.boolean().refine((v) => v === true, {
    message: 'You must confirm you are 18+',
  }),
  terms: z.boolean().refine((v) => v === true, {
    message: 'You must accept the terms',
  }),
});

type FormData = z.infer<typeof schema>;

export default function RegisterPage() {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState('');
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  async function onSubmit(data: FormData) {
    setServerError('');
    try {
      const tokens = await registerUser({
        email: data.email,
        username: data.username,
        password: data.password,
        date_of_birth: data.date_of_birth,
        citizenship_attested: data.is_us_citizen,
        age_attested: data.age_confirm,
        terms_attested: data.terms,
        monthly_income: data.monthly_income ? parseFloat(data.monthly_income) : undefined,
      });
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);
      const user = await getMe();
      setUser(user);
      navigate('/dashboard');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setServerError(detail.map((d: any) => d.msg).join(' · '));
      } else {
        setServerError(detail || 'Registration failed. Please try again.');
      }
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-center gap-2 mb-8">
          <TrendingUp className="w-8 h-8 text-indigo-400" />
          <span className="text-2xl font-bold text-white">InvestIQ</span>
        </div>

        <div className="bg-gray-800 rounded-2xl border border-gray-700 p-8">
          <h1 className="text-xl font-semibold text-white mb-1">Create your account</h1>
          <p className="text-sm text-gray-400 mb-6">Start simulating your investment strategy</p>

          {serverError && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-sm text-red-300">
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
            <Input
              label="Email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              error={errors.email?.message}
              {...register('email')}
            />
            <Input
              label="Username"
              type="text"
              autoComplete="username"
              placeholder="yourname"
              error={errors.username?.message}
              {...register('username')}
            />
            <Input
              label="Password"
              type="password"
              autoComplete="new-password"
              placeholder="Min 8 chars, 1 uppercase, 1 number"
              error={errors.password?.message}
              {...register('password')}
            />
            <Input
              label="Date of Birth"
              type="date"
              error={errors.date_of_birth?.message}
              hint="You must be 18 or older"
              {...register('date_of_birth')}
            />
            <Input
              label="Monthly Income (optional)"
              type="number"
              prefix="$"
              placeholder="5000"
              hint="Used only to calculate investment recommendations"
              error={errors.monthly_income?.message}
              {...register('monthly_income')}
            />

            {/* Verification checkboxes */}
            <div className="bg-gray-900 rounded-xl border border-gray-700 p-4 flex flex-col gap-3 mt-1">
              <div className="flex items-center gap-2 text-sm text-gray-300">
                <ShieldCheck className="w-4 h-4 text-indigo-400 shrink-0" />
                <span className="font-medium text-gray-200">Account verification</span>
              </div>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-indigo-500 w-4 h-4"
                  {...register('is_us_citizen')}
                />
                <span className="text-sm text-gray-300">
                  I confirm I am a{' '}
                  <strong className="text-white">United States citizen</strong> or permanent
                  resident
                </span>
              </label>
              {errors.is_us_citizen && (
                <p className="text-xs text-red-400 -mt-1">{errors.is_us_citizen.message}</p>
              )}

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-indigo-500 w-4 h-4"
                  {...register('age_confirm')}
                />
                <span className="text-sm text-gray-300">
                  I confirm I am at least <strong className="text-white">18 years of age</strong>
                </span>
              </label>
              {errors.age_confirm && (
                <p className="text-xs text-red-400 -mt-1">{errors.age_confirm.message}</p>
              )}

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-indigo-500 w-4 h-4"
                  {...register('terms')}
                />
                <span className="text-sm text-gray-300">
                  I understand this is for{' '}
                  <strong className="text-white">educational purposes only</strong> and not financial advice
                </span>
              </label>
              {errors.terms && (
                <p className="text-xs text-red-400 -mt-1">{errors.terms.message}</p>
              )}
            </div>

            <Button type="submit" size="lg" loading={isSubmitting} className="mt-2 w-full">
              Create Account
            </Button>
          </form>

          <p className="text-sm text-gray-400 text-center mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-indigo-400 hover:text-indigo-300">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
