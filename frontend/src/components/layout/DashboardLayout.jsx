import { useAuth } from '../../context/AuthContext';
import Sidebar from './Sidebar';
import { useNavigate } from 'react-router-dom';

export default function DashboardLayout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        {/* Top bar */}
        <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between shadow-sm">
          <div className="text-sm text-slate-500">
            Welcome back,{' '}
            <span className="font-semibold text-slate-800">
              {user?.username || 'Admin'}
            </span>
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            Logout
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

