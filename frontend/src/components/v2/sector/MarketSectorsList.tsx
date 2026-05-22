import { useNavigate } from 'react-router-dom';
import { SECTOR_AGGREGATES, SECTOR_TAGLINE } from '../../../data/mockSector';

interface Props {
  activeSlug: string;
}

export function MarketSectorsList({ activeSlug }: Props) {
  const navigate = useNavigate();
  const sorted = [...SECTOR_AGGREGATES].sort((a, b) => b.pressure - a.pressure);

  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper">
      <div className="px-4 py-3 border-b border-fr-line">
        <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-gold">Market Sectors</div>
      </div>
      <ul className="p-3 space-y-2">
        {sorted.map((s) => {
          const active = s.slug === activeSlug;
          return (
            <li key={s.slug}>
              <button
                type="button"
                onClick={() => navigate(`/markets/${s.slug}`)}
                className={`w-full text-left rounded-lg border px-3.5 py-3 transition-colors ${
                  active
                    ? 'border-fr-blue/40 bg-fr-blue-tint'
                    : 'border-fr-line bg-fr-paper hover:bg-fr-paper-2 hover:border-fr-line-strong'
                }`}
              >
                <div className="flex items-start justify-between gap-3 mb-1">
                  <span className={`text-[13.5px] font-semibold ${active ? 'text-fr-ink' : 'text-fr-ink'}`}>
                    {s.label}
                  </span>
                  <span className={`text-[12px] font-mono tabular-nums ${active ? 'text-fr-blue' : 'text-fr-ink-mute'}`}>
                    {s.pressure}
                  </span>
                </div>
                <div className="text-[11.5px] text-fr-ink-mute leading-snug">
                  {SECTOR_TAGLINE[s.slug] ?? '—'}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
