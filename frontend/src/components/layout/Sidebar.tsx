import { NavLink } from 'react-router-dom';

const NAV = [
  { label: 'Dashboard', to: '/dashboard', icon: 'FR' },
  { label: 'Console', to: '/console', icon: 'CO' },
  { label: 'Heatmap', to: '/heatmap', icon: 'HM' },
  { label: 'Validation', to: '/validation', icon: 'VL' },
];

export function Sidebar() {
  return (
    <aside className="w-[82px] shrink-0 flex flex-col items-center border-r border-orbital-border bg-[rgba(5,6,7,0.78)] py-6 gap-[22px]">
      {/* Brand mark */}
      <div className="w-[34px] h-[34px] rounded-full border border-[rgba(210,184,113,0.46)] relative mb-2"
        style={{ boxShadow: '0 0 24px rgba(215,180,106,.24)' }}
      >
        <div className="absolute inset-[7px] rounded-full border border-[rgba(215,180,106,.4)]" />
        <div className="absolute inset-[15px] rounded-full bg-[#d7b46a]" style={{ boxShadow: '0 0 18px #d7b46a' }} />
      </div>

      {/* Nav items */}
      <nav className="flex-1 flex flex-col items-center gap-[14px]">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `relative flex items-center justify-center w-10 h-10 rounded-[14px] border font-mono text-[12px] transition-all group ${
                isActive
                  ? 'text-[#d7b46a] border-[rgba(210,184,113,0.46)] bg-[rgba(215,180,106,0.09)]'
                    + ' shadow-[inset_0_0_18px_rgba(215,180,106,.09),0_0_24px_rgba(215,180,106,.11)]'
                  : 'text-[#8e9994] border-[rgba(184,198,192,0.16)] bg-[rgba(255,255,255,.03)] hover:bg-[rgba(255,255,255,.06)] hover:text-[#edf2ef]'
              }`
            }
            title={item.label}
          >
            {item.icon}
            {/* Tooltip */}
            <span className="absolute left-[52px] px-2 py-1 rounded bg-[#101418] border border-orbital-border text-[11px] text-[#edf2ef] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              {item.label}
            </span>
          </NavLink>
        ))}
      </nav>

      {/* Footer version */}
      <span className="text-[9px] text-[#59635f] font-mono">v2.0</span>
    </aside>
  );
}