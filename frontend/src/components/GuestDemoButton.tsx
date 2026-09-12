import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { startGuestSession, getMe } from '../api/auth';
import { setUser } from '../store/auth';

/**
 * Starts a demo session and drops the visitor straight into the dashboard.
 *
 * The session is a real, isolated user row — every downstream route behaves
 * exactly as it does for a signed-up account. The only difference is the
 * is_guest flag, which the UI uses to label the data as sample.
 */
export function GuestDemoButton({ className = '' }: { className?: string }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function start() {
    setLoading(true);
    setError('');
    try {
      const tokens = await startGuestSession();
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);
      setUser(await getMe());
      navigate('/');
    } catch {
      setError('Could not start the demo. Is the backend running on port 8000?');
      setLoading(false);
    }
  }

  return (
    <div className={className}>
      <button
        type="button"
        onClick={start}
        disabled={loading}
        className="w-full px-4 py-2.5 rounded-lg border border-gray-600 bg-transparent
                   text-gray-200 text-sm font-medium hover:bg-gray-800
                   disabled:opacity-50 transition-colors"
      >
        {loading ? 'Starting demo…' : 'Try the guest demo'}
      </button>
      <p className="text-xs text-gray-500 mt-2 text-center">
        No account, no email. Sample data, cleared when you log out.
      </p>
      {error && <p className="text-xs text-red-400 mt-2 text-center">{error}</p>}
    </div>
  );
}
