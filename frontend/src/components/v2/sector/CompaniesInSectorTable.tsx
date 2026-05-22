import { useNavigate } from 'react-router-dom';
import type { SectorAggregate, SectorCompany } from '../../../data/mockSector';

interface Props {
  sector: SectorAggregate;
}

const TREND_STYLE: Record<SectorCompany['trend'], { label: string; cls: string }> = {
  rising: { label: 'Rising', cls: 'text-orange-700 bg-orange-50 border-orange-200' },
  moderate: { label: 'Moderate', cls: 'text-amber-700 bg-amber-50 border-amber-200' },
  stable: { label: 'Stable', cls: 'text-slate-600 bg-slate-50 border-slate-200' },
  easing: { label: 'Easing', cls: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
};

export function CompaniesInSectorTable({ sector }: Props) {
  const navigate = useNavigate();

  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper">
      <div className="px-5 py-4 border-b border-fr-line flex items-start justify-between gap-4">
        <div>
          <div className="text-[14px] font-semibold text-fr-ink">Companies in {sector.label}</div>
          <div className="text-[11px] text-fr-ink-mute mt-0.5">
            Ranked by organizational pressure and signal velocity.
          </div>
        </div>
        <button
          type="button"
          onClick={() => navigate('/markets')}
          className="text-[11.5px] font-medium text-fr-ink-mute hover:text-fr-ink border border-fr-line rounded-md px-3 py-1.5"
        >
          Back to Sector Overview
        </button>
      </div>

      <div className="grid grid-cols-[1.4fr_2fr_120px_140px_100px] px-5 py-2.5 text-[10px] font-mono tracking-[0.1em] uppercase text-fr-ink-faint border-b border-fr-line bg-fr-paper-2">
        <div>Company</div>
        <div>Primary pain</div>
        <div>Pressure</div>
        <div>Trend</div>
        <div></div>
      </div>

      <ul className="divide-y divide-fr-line">
        {sector.companies.map((c) => {
          const trend = TREND_STYLE[c.trend];
          return (
            <li
              key={c.id}
              className="grid grid-cols-[1.4fr_2fr_120px_140px_100px] items-center px-5 py-3 hover:bg-fr-paper-2 transition-colors"
            >
              <div>
                <div className="text-[13px] font-semibold text-fr-ink">{c.name}</div>
                <div className="text-[10px] font-mono tracking-wide text-fr-ink-faint uppercase mt-0.5">{sector.slug}</div>
              </div>
              <div className="text-[12.5px] text-fr-ink-soft">{c.primaryPain}</div>
              <div className="text-[14px] font-semibold text-fr-ink tabular-nums">{c.pressure}</div>
              <div>
                <span className={`inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full border ${trend.cls}`}>
                  {trend.label}
                </span>
              </div>
              <div>
                <button
                  type="button"
                  onClick={() => navigate(`/markets/${sector.slug}/c/${c.id}`)}
                  className="text-[12px] font-semibold text-fr-gold border border-fr-gold-soft rounded-md px-3 py-1 hover:bg-fr-gold-tint transition-colors"
                >
                  Open
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
