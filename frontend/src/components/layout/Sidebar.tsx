import { NavLink } from 'react-router-dom';

const NAV = [
  { label: 'Dashboard', to: '/dashboard', icon: '⬛' },
  { label: 'Heatmap', to: '/heatmap', icon: '▦' },
  { label: 'Validation', to: '/validation', icon: '⬜' },
];

export function Sidebar() {
  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-gray-100">
        <span className="text-sm font-bold tracking-tight text-gray-900">
          Friction Radar
        </span>
        <span className="ml-2 text-xs text-gray-400 font-medium">internal</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? 'bg-gray-100 text-gray-900 font-medium'
                  : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
              }`
            }
          >
            <span className="text-xs opacity-60">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer hint */}
      <div className="px-4 py-3 border-t border-gray-100">
        <p className="text-xs text-gray-400">MVP v0.3</p>
      </div>
    </aside>
  );
}
