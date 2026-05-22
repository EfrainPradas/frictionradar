import { createPortal } from 'react-dom';
import type { HeatmapCell, HeatmapMode } from '../../../data/mockHeatmap';
import { SECTORS, FUNCTIONS, RADAR_DIMENSIONS } from '../../../data/taxonomy';

interface Props {
  cell: HeatmapCell;
  mode: HeatmapMode;
  x: number;
  y: number;
}

function labelFor(slug: string, kind: 'sector' | 'function'): string {
  const source = kind === 'sector' ? SECTORS : FUNCTIONS;
  return source.find((s) => s.slug === slug)?.label ?? slug;
}

function dimLabel(slug: string): string {
  return RADAR_DIMENSIONS.find((d) => d.slug === slug)?.label ?? slug;
}

function velocityBadge(v: number): { text: string; cls: string } {
  if (v > 0.4) return { text: 'Accelerating', cls: 'bg-orange-100 text-orange-800 border-orange-300' };
  if (v > 0.1) return { text: 'Rising', cls: 'bg-amber-100 text-amber-800 border-amber-300' };
  if (v < -0.4) return { text: 'Easing fast', cls: 'bg-emerald-100 text-emerald-800 border-emerald-300' };
  if (v < -0.1) return { text: 'Easing', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
  return { text: 'Stable', cls: 'bg-slate-100 text-slate-700 border-slate-300' };
}

export function HeatmapTooltip({ cell, mode, x, y }: Props) {
  const TOOLTIP_W = 300;
  const PADDING = 12;
  const left = Math.min(window.innerWidth - TOOLTIP_W - PADDING, Math.max(PADDING, x + 14));
  const top = Math.max(PADDING, y - 8);
  const vel = velocityBadge(cell.velocity);

  return createPortal(
    <div
      className="pointer-events-none fixed z-[9999] rounded-xl border-2 border-slate-300 overflow-hidden"
      style={{
        top,
        left,
        width: TOOLTIP_W,
        background: '#ffffff',
        boxShadow: '0 24px 48px -12px rgba(15,23,42,0.35), 0 8px 16px -4px rgba(15,23,42,0.18)',
      }}
    >
      <div className="px-4 pt-3.5 pb-2.5 bg-slate-900 text-white">
        <div className="text-[10px] font-mono tracking-[0.14em] uppercase text-slate-400 font-semibold">
          Market Cell
        </div>
        <div className="text-[14px] font-bold mt-1 leading-snug">
          {labelFor(cell.sector, 'sector')} <span className="text-slate-400">×</span>{' '}
          {labelFor(cell.function, 'function')}
        </div>
      </div>

      <div className="px-4 py-3 grid grid-cols-3 gap-3 bg-white">
        <Stat label="Pain" value={cell.intensity} active={mode === 'intensity'} />
        <Stat label="Velocity" value={cell.velocity > 0 ? `+${Math.round(cell.velocity * 100)}` : Math.round(cell.velocity * 100)} active={mode === 'velocity'} />
        <Stat label="Opp" value={cell.opportunity} active={mode === 'opportunity'} />
      </div>

      <div className="px-4 pb-3 flex items-center justify-between gap-2 bg-white">
        <span className={`inline-flex items-center text-[10.5px] font-bold px-2 py-0.5 rounded-full border ${vel.cls}`}>
          {vel.text}
        </span>
        <span className="text-[11px] text-slate-700">
          <span className="font-bold text-slate-900">{cell.companyCount}</span> companies
        </span>
      </div>

      <div className="px-4 py-2.5 bg-slate-50 border-t border-slate-200">
        <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-slate-500 font-semibold mb-1">
          Dominant pain
        </div>
        <div className="text-[12.5px] font-semibold text-slate-900">{dimLabel(cell.dominantDimension)}</div>
      </div>

      {cell.notableSignals.length > 0 && (
        <div className="px-4 py-2.5 border-t border-slate-200 bg-white">
          <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-slate-500 font-semibold mb-1.5">
            Notable signals
          </div>
          <ul className="space-y-1">
            {cell.notableSignals.map((s) => (
              <li key={s} className="text-[11.5px] text-slate-700 leading-snug flex gap-1.5">
                <span className="text-slate-400 font-bold">›</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="px-4 py-2.5 bg-gradient-to-r from-amber-50 to-amber-100 border-t-2 border-amber-300 text-[11px] font-bold text-amber-900 text-center tracking-wide">
        Click to open {labelFor(cell.sector, 'sector')} sector →
      </div>
    </div>,
    document.body,
  );
}

function Stat({ label, value, active }: { label: string; value: number | string; active: boolean }) {
  return (
    <div
      className={`rounded-md px-2 py-1.5 ${
        active ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-900'
      }`}
    >
      <div className={`text-[9px] font-mono tracking-[0.1em] uppercase font-semibold ${active ? 'text-amber-300' : 'text-slate-500'}`}>
        {label}
      </div>
      <div className="text-[16px] font-bold tabular-nums leading-tight">{value}</div>
    </div>
  );
}
