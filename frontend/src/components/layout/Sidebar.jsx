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
    <aside className="w-64 flex-shrink-0 bg-ink-900 text-white flex flex-col h-full overflow-y-auto">
      <div className="weave h-1.5 flex-shrink-0" />

      {/* Brand */}
      <div className="px-4 pt-4 pb-3">
        <img
          src="/norman-logo-small.webp"
          alt="Norman Cellphone Center & Accessories"
          className="w-full rounded-md ring-1 ring-white/10"
        />
        <p className="mt-2 font-display text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">
          Staff dashboard
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-3 space-y-0.5">
        {navItems.map((item) =>
          item.enabled ? (
            <NavLink
              key={item.label}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 pl-3 pr-2 py-2.5 rounded-md text-sm font-semibold border-l-4 transition-colors ${
                  isActive
                    ? 'border-brand-500 bg-white/10 text-white'
                    : 'border-transparent text-stone-300 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              {item.label}
              {item.badge && (
                <span className="ml-auto text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300">
                  {item.badge}
                </span>
              )}
            </NavLink>
          ) : (
            <span
              key={item.label}
              className="flex items-center gap-3 pl-4 pr-2 py-2.5 text-sm text-stone-600 cursor-not-allowed"
              title="Coming soon"
            >
              {item.label}
            </span>
          ),
        )}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-white/10 text-xs text-stone-500 leading-relaxed">
        Maddela Public Market
        <br />
        Maddela, Quirino
      </div>
    </aside>
  );
}
