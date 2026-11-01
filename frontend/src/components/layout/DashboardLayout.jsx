import { useAuth } from '../../context/AuthContext';
import Sidebar from './Sidebar';
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
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="bg-white border-b border-stone-200 px-6 py-3 flex items-center justify-between">
          <div className="text-sm text-stone-500">
            Signed in as{' '}
            <span className="font-semibold text-stone-800">
              {user?.username || 'Admin'}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <AiSwitch />
            <button
              onClick={handleLogout}
              className="px-3 py-1.5 text-sm font-semibold text-stone-600 border border-stone-300 hover:border-stone-400 hover:text-stone-900 rounded-md transition-colors"
            >
              Log out
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 min-h-0 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

