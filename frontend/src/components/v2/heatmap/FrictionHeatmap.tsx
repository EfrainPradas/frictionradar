import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SECTORS, FUNCTIONS } from '../../../data/taxonomy';
import { HEATMAP_CELLS, type HeatmapCell, type HeatmapMode } from '../../../data/mockHeatmap';
import { colorForCell, textInkFor } from './palette';
import { HeatmapTooltip } from './HeatmapTooltip';
import { CellIntelligenceView } from './CellIntelligenceView';

interface Props {
  mode: HeatmapMode;
}

interface HoverState {
  cell: HeatmapCell;
  x: number;
  y: number;
}

export function FrictionHeatmap({ mode }: Props) {
  const navigate = useNavigate();
  const [hover, setHover] = useState<HoverState | null>(null);
  const [selectedCell, setSelectedCell] = useState<HeatmapCell | null>(null);

  const cellMap = useMemo(() => {
    const m = new Map<string, HeatmapCell>();
    for (const c of HEATMAP_CELLS) m.set(`${c.sector}::${c.function}`, c);
    return m;
  }, []);

  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper overflow-hidden">
      <div className="overflow-auto">
        <table className="border-collapse" style={{ tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: 180 }} />
            {FUNCTIONS.map((f) => (
              <col key={f.slug} style={{ width: 88 }} />
            ))}
          </colgroup>

          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-20 bg-fr-paper border-b border-fr-line px-4 py-3 text-left">
                <div className="text-[10px] font-mono tracking-[0.1em] uppercase text-fr-ink-faint">Sector ↓ / Function →</div>
              </th>
              {FUNCTIONS.map((f) => (
                <th
                  key={f.slug}
                  className="sticky top-0 z-10 bg-fr-paper border-b border-fr-line px-2 py-3 text-left align-bottom"
                >
                  <div
                    className="text-[11px] font-semibold text-fr-ink-soft whitespace-nowrap leading-tight"
                    style={{
                      writingMode: 'vertical-rl',
                      transform: 'rotate(180deg)',
                      height: 90,
                    }}
                  >
                    {f.label}
                  </div>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {SECTORS.map((s, rowIdx) => (
              <tr key={s.slug} className={rowIdx % 2 === 0 ? '' : 'bg-fr-paper-2'}>
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-fr-paper border-r border-fr-line px-2 py-2 text-left"
                >
                  <button
                    type="button"
                    onClick={() => navigate(`/markets/${s.slug}`)}
                    className="w-full text-left px-2 py-1 rounded-md text-[12.5px] font-semibold text-fr-ink whitespace-nowrap hover:bg-fr-gold-tint hover:text-fr-gold transition-colors"
                    title={`Open ${s.label} sector overview`}
                  >
                    {s.label}
                  </button>
                </th>

                {FUNCTIONS.map((f) => {
                  const cell = cellMap.get(`${s.slug}::${f.slug}`);
                  if (!cell) {
                    return <td key={f.slug} className="p-1.5"><div className="h-12 rounded bg-fr-line/40" /></td>;
                  }
                  const bg = colorForCell(mode, cell.intensity, cell.velocity, cell.opportunity);
                  const ink = textInkFor(bg);
                  const value =
                    mode === 'intensity'
                      ? cell.intensity
                      : mode === 'opportunity'
                      ? cell.opportunity
                      : cell.velocity > 0
                      ? `+${Math.round(cell.velocity * 100)}`
                      : Math.round(cell.velocity * 100);
                  return (
                    <td key={f.slug} className="p-1">
                      <button
                        type="button"
                        onMouseEnter={(e) => {
                          const r = (e.currentTarget as HTMLButtonElement).getBoundingClientRect();
                          setHover({ cell, x: r.right, y: r.top });
                        }}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => setSelectedCell(cell)}
                        className="w-full h-12 rounded-md flex items-center justify-center text-[12px] font-semibold transition-transform hover:scale-[1.04] hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-fr-blue-soft"
                        style={{ background: bg, color: ink }}
                      >
                        {value}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hover && <HeatmapTooltip cell={hover.cell} mode={mode} x={hover.x} y={hover.y} />}

      {selectedCell && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20" onClick={() => setSelectedCell(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <CellIntelligenceView
              cell={{
                sector: selectedCell.sector,
                sectorLabel: SECTORS.find((s) => s.slug === selectedCell.sector)?.label ?? selectedCell.sector,
                function: selectedCell.function,
                functionLabel: FUNCTIONS.find((f) => f.slug === selectedCell.function)?.label ?? selectedCell.function,
                intensity: selectedCell.intensity,
                velocity: selectedCell.velocity,
                opportunity: selectedCell.opportunity,
                companyCount: selectedCell.companyCount,
                dominantPain: selectedCell.dominantDimension,
                notableSignals: selectedCell.notableSignals,
              }}
              onClose={() => setSelectedCell(null)}
              onCompanyClick={(companyId) => {
                setSelectedCell(null);
                navigate(`/markets/${selectedCell.sector}/c/${companyId}`);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
