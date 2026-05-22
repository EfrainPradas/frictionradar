import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { SECTOR_AGGREGATES } from '../../../data/mockSector';

interface NavItem {
  label: string;
  to: string;
  icon: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  {
    label: 'Intelligence',
    items: [
      { label: 'Market Heatmap', to: '/markets', icon: 'H' },
      { label: 'VIP Opportunities', to: '/opportunities', icon: 'V' },
      { label: 'Brief Center', to: '/briefs', icon: 'B' },
    ],
  },
  {
    label: 'System',
    items: [{ label: 'Pipeline Ops', to: '/settings', icon: '⚙' }],
  },
];

export function SidebarV2() {
  const location = useLocation();
  const sectorsOpen = location.pathname.startsWith('/markets/') || location.pathname === '/markets';
  const [expanded, setExpanded] = useState(sectorsOpen);
  const topSectors = [...SECTOR_AGGREGATES].sort((a, b) => b.pressure - a.pressure);

  return (
    <aside className="w-[240px] shrink-0 border-r border-fr-line bg-fr-paper flex flex-col">
      <div className="px-5 py-5 border-b border-fr-line">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-fr-ink flex items-center justify-center">
            <span className="text-fr-paper text-[11px] font-bold tracking-[0.08em]">FR</span>
          </div>
          <div className="leading-tight">
            <div className="text-[13px] font-semibold text-fr-ink">FrictionRadar</div>
            <div className="text-[10px] text-fr-ink-mute tracking-[0.06em]">Intelligence Platform</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-auto px-3 py-4 flex flex-col gap-4">
        <Group label={GROUPS[0].label}>
          {GROUPS[0].items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/markets'}
              className={({ isActive }) => navItemCls(isActive)}
            >
              <span className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-mono bg-fr-overlay text-fr-ink-soft">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}

          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className={`flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
              expanded ? 'text-fr-ink' : 'text-fr-ink-soft'
            } hover:bg-fr-overlay/60`}
          >
            <span className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-mono bg-fr-overlay text-fr-ink-soft">
              ◆
            </span>
            <span className="flex-1 text-left font-medium">Sectors</span>
            <span className="text-[10px] text-fr-ink-faint">{expanded ? '▾' : '▸'}</span>
          </button>

          {expanded && (
            <ul className="ml-3 mt-1 mb-1 border-l border-fr-line pl-3 flex flex-col gap-0.5">
              {topSectors.map((s) => (
                <li key={s.slug}>
                  <NavLink
                    to={`/markets/${s.slug}`}
                    className={({ isActive }) =>
                      `flex items-center justify-between gap-2 px-2 py-1.5 rounded text-[12px] transition-colors ${
                        isActive
                          ? 'bg-fr-gold-tint text-fr-ink font-semibold'
                          : 'text-fr-ink-mute hover:text-fr-ink hover:bg-fr-overlay/60'
                      }`
                    }
                  >
                    <span className="truncate">{s.label}</span>
                    <span className="text-[10px] font-mono tabular-nums text-fr-ink-faint">{s.pressure}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          )}
        </Group>

        <Group label={GROUPS[1].label}>
          {GROUPS[1].items.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => navItemCls(isActive)}>
              <span className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-mono bg-fr-overlay text-fr-ink-soft">
                {item.icon}
              </span>
              {item.label}
            </NavLink>
          ))}
        </Group>
      </nav>

      <div className="px-4 py-3 border-t border-fr-line text-[10px] text-fr-ink-faint tracking-wide">
        <a href="/legacy/dashboard" className="hover:text-fr-ink-mute">View legacy →</a>
      </div>
    </aside>
  );
}

function navItemCls(isActive: boolean) {
  return `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
    isActive ? 'bg-fr-overlay text-fr-ink font-semibold' : 'text-fr-ink-soft hover:bg-fr-overlay/60 hover:text-fr-ink'
  }`;
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="px-3 text-[10px] font-mono tracking-[0.14em] uppercase text-fr-ink-faint mb-0.5">{label}</div>
      {children}
    </div>
  );
}
