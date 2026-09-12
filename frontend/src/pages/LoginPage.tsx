import { useState } from 'react';
import { GuestDemoButton } from '../components/GuestDemoButton';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TrendingUp } from 'lucide-react';
import { login } from '../api/auth';
import { setUser } from '../store/auth';
import { getMe } from '../api/auth';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';

const schema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(1, 'Password is required'),
});

type FormData = z.infer<typeof schema>;

export default function LoginPage() {
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
      const tokens = await login(data);
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);
      const user = await getMe();
      setUser(user);
      navigate('/');
    } catch (err: any) {
      setServerError(err.response?.data?.detail || 'Login failed. Check your credentials.');
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <TrendingUp className="w-8 h-8 text-indigo-400" />
          <span className="text-2xl font-bold text-white">InvestIQ</span>
        </div>

        <div className="bg-gray-800 rounded-2xl border border-gray-700 p-8">
          <h1 className="text-xl font-semibold text-white mb-1">Welcome back</h1>
          <p className="text-sm text-gray-400 mb-6">Sign in to your account</p>

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
              label="Password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              error={errors.password?.message}
              {...register('password')}
            />
            <Button type="submit" size="lg" loading={isSubmitting} className="mt-2 w-full">
              Sign in
            </Button>
          </form>

          <div className="flex items-center gap-3 my-6">
            <div className="h-px flex-1 bg-gray-700" />
            <span className="text-xs text-gray-500">or</span>
            <div className="h-px flex-1 bg-gray-700" />
          </div>

          <GuestDemoButton />

          <p className="text-sm text-gray-400 text-center mt-6">
            Don't have an account?{' '}
            <Link to="/register" className="text-indigo-400 hover:text-indigo-300">
              Create one
            </Link>
          </p>
        </div>

        <p className="text-xs text-gray-600 text-center mt-4">
          This platform is for educational purposes only. Not financial advice.
        </p>
      </div>
    </div>
  );
}
