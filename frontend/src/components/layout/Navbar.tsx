import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { logout } from '../../store/auth';
import { TrendingUp, LogOut, BookOpen, BarChart2, ShieldAlert, Bot, FlaskConical } from 'lucide-react';
import { ThemeToggle } from '../ui/ThemeToggle';

export function Navbar() {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  const isActive = (path: string) =>
    location.pathname === path
      ? 'text-indigo-400 bg-indigo-900/30'
      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800';

  return (
    <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-900/80 backdrop-blur">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 text-white font-bold text-lg">
          <TrendingUp className="w-5 h-5 text-indigo-400" />
          <span className="hidden sm:inline">InvestIQ</span>
        </Link>

        {/* Nav links (authenticated) */}
        {isAuthenticated && (
          <div className="flex items-center gap-1">
            <Link
              to="/dashboard"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${isActive('/dashboard')}`}
            >
              <BarChart2 className="w-4 h-4" />
              <span className="hidden sm:inline">Simulate</span>
            </Link>
            <Link
              to="/compare"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${isActive('/compare')}`}
            >
              <BarChart2 className="w-4 h-4" />
              <span className="hidden sm:inline">Compare</span>
            </Link>
            <Link
              to="/risk"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${isActive('/risk')}`}
            >
              <ShieldAlert className="w-4 h-4" />
              <span className="hidden sm:inline">Risk desk</span>
            </Link>
            <Link to="/research" aria-label="BTC research desk" className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm ${isActive('/research')}`}><FlaskConical className="w-4 h-4" /><span className="hidden sm:inline">Research</span></Link>
            <Link
              to="/agent"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${isActive('/agent')}`}
            >
              <Bot className="w-4 h-4" />
              <span className="hidden sm:inline">Agent desk</span>
            </Link>
            <Link
              to="/scenarios"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${isActive('/scenarios')}`}
            >
              <BookOpen className="w-4 h-4" />
              <span className="hidden sm:inline">Saved</span>
            </Link>
          </div>
        )}

        {/* Right side */}
        <div className="flex items-center gap-2">
          <ThemeToggle />
          {isAuthenticated ? (
            <>
              <span className="hidden sm:inline text-sm text-gray-400">
                {user?.username}
              </span>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
                aria-label="Log out"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Logout</span>
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200 transition-colors"
              >
                Log in
              </Link>
              <Link
                to="/register"
                className="px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
