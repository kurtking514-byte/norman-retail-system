import { useAuth } from '../../context/AuthContext';
import Sidebar from './Sidebar';
import ShopBanner from './ShopBanner';
import AiSwitch from '../common/AiSwitch';
import { useNavigate } from 'react-router-dom';

export default function DashboardLayout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <ShopBanner />
      <div className="flex flex-shrink-0 items-center justify-between gap-4 bg-ink-900 px-6 py-2 text-sm text-white">
        <span className="font-display text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">
          Staff dashboard
        </span>
        <div className="flex items-center gap-5">
          <span className="hidden md:inline text-stone-400">
            Signed in as <span className="font-semibold text-white">{user?.username || 'Admin'}</span>
          </span>
          <AiSwitch onDark />
          <button
            onClick={handleLogout}
            className="px-3 py-1 font-semibold text-white border border-white/25 hover:bg-white/10 rounded-md transition-colors"
          >
            Log out
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 min-h-0 min-w-0 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
