import { useState } from 'react';
import { Navigate, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ShopBanner from '../components/layout/ShopBanner';

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // If already authenticated, redirect away
  if (isAuthenticated) {
    const from = location.state?.from?.pathname || '/dashboard';
    return <Navigate to={from} replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password.');
      return;
    }

    setLoading(true);
    try {
      await login(username, password);
      const from = location.state?.from?.pathname || '/dashboard';
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    'w-full px-3 py-2.5 border border-stone-300 rounded-md text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500';

  return (
    <div className="min-h-screen bg-stone-100 flex flex-col">
      <ShopBanner tagline="Retailer of authentic mobile phones and accessories" />
      <div className="flex-1 flex items-start sm:items-center justify-center px-4 py-10">
        <div className="w-full max-w-md bg-white rounded-lg border border-stone-200 shadow-xl overflow-hidden">
          <div className="weave h-1.5" />
          <div className="p-6 sm:p-10">
            <h1 className="text-3xl text-stone-900">Staff sign in</h1>
            <p className="mt-1 mb-6 text-sm text-stone-500">Inventory, reservations, repairs and customer chats.</p>

            {error && (
              <div className="mb-4 px-4 py-3 bg-brand-50 border border-brand-200 text-brand-800 text-sm rounded-md">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="username" className="block text-sm font-semibold text-stone-700 mb-1">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={inputClass}
                  autoComplete="username"
                  autoFocus
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-semibold text-stone-700 mb-1">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputClass}
                  autoComplete="current-password"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-md text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 disabled:bg-brand-300 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Signing in...
                  </span>
                ) : (
                  'Sign in'
                )}
              </button>
            </form>
          </div>
        </div>
      </div>
      <p className="pb-6 text-center text-xs text-stone-500">
        Maddela Public Market, Maddela, Quirino
      </p>
    </div>
  );
}
