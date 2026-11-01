import { NavLink } from 'react-router-dom';

const navItems = [
  { label: 'Dashboard', path: '/dashboard', enabled: true },
  { label: 'Inventory', path: '/inventory', enabled: true },
  { label: 'Reservations', path: '/reservations', enabled: true },
  { label: 'Repairs', path: '/repairs', enabled: true, badge: 'In development' },
  { label: 'Live Chat', path: '/live-chat', enabled: true },
  { label: 'Settings', path: '#', enabled: false },
];

export default function Sidebar() {
  return (
    <aside className="w-64 flex-shrink-0 bg-slate-800 text-white flex flex-col h-full overflow-y-auto">
      {/* Brand */}
      <div className="px-6 py-5 border-b border-slate-700">
        <h1 className="text-lg font-bold tracking-tight">
          <span className="text-blue-400">Norman</span> Admin
        </h1>
        <p className="text-xs text-slate-400 mt-0.5">Cellphone Center &amp; Repair</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) =>
          item.enabled ? (
            <NavLink
              key={item.label}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                }`
              }
            >
              {item.label}
              {item.badge && (
                <span className="ml-auto text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-400/20 text-amber-300">
                  {item.badge}
                </span>
              )}
            </NavLink>
          ) : (
            <span
              key={item.label}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-500 cursor-not-allowed"
              title="Coming in Phase 7"
            >
              {item.label}
            </span>
          ),
        )}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-slate-700 text-xs text-slate-500">
        v1.0
      </div>
    </aside>
  );
}


