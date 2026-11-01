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
      <ShopBanner>
        <div className="flex items-center gap-4 rounded-md bg-ink-900/75 px-4 py-2 text-sm text-white backdrop-blur-sm">
          <span className="hidden md:inline text-stone-300">
            Signed in as <span className="font-semibold text-white">{user?.username || 'Admin'}</span>
          </span>
          <AiSwitch onDark />
          <button
            onClick={handleLogout}
            className="px-3 py-1 font-semibold text-white border border-white/30 hover:bg-white/10 rounded-md transition-colors"
          >
            Log out
          </button>
        </div>
      </ShopBanner>

      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 min-h-0 min-w-0 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
