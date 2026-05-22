import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { getSectorAggregate } from '../../data/mockSector';
import { FUNCTIONS } from '../../data/taxonomy';
import { SectorPressureKPIs } from '../../components/v2/sector/SectorPressureKPIs';
import { MarketSectorsList } from '../../components/v2/sector/MarketSectorsList';
import { FrictionRadar } from '../../components/v2/sector/FrictionRadar';
import { SectorInterpretation } from '../../components/v2/sector/SectorInterpretation';
import { CompaniesInSectorTable } from '../../components/v2/sector/CompaniesInSectorTable';

export function SectorOverviewPage() {
  const { sector: slug } = useParams();
  const [searchParams] = useSearchParams();
  const fnSlug = searchParams.get('fn');
  const fnLabel = fnSlug ? FUNCTIONS.find((f) => f.slug === fnSlug)?.label : null;
  const sector = slug ? getSectorAggregate(slug) : undefined;

  if (!sector) return <Navigate to="/markets" replace />;

  return (
    <div className="p-7 flex flex-col gap-5 max-w-[1280px] mx-auto">
      <header className="flex items-start justify-between gap-6 rounded-lg border border-fr-line bg-fr-paper p-6">
        <div className="min-w-0">
          <div className="text-[11px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint mb-1">
            Sector Overview
          </div>
          <h1 className="text-[26px] font-semibold text-fr-ink leading-tight">{sector.label} Market Intelligence</h1>
          {fnLabel && (
            <div className="inline-flex items-center gap-1.5 mt-2 px-2.5 py-1 rounded-full bg-fr-gold-tint text-fr-gold text-[11px] font-semibold">
              <span className="text-fr-ink-faint font-normal">From heatmap ·</span> {sector.label} × {fnLabel}
            </div>
          )}
          <p className="text-[13px] text-fr-ink-mute mt-2 max-w-2xl leading-relaxed">
            Macro view of organizational friction across the {sector.label.toLowerCase()} sector. Start at the sector level,
            identify companies under pressure, then drill into one company, and to specific organizational pain.
          </p>
        </div>
        <div className="flex flex-col items-end gap-3 shrink-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="text-[12px] font-medium text-fr-ink-soft border border-fr-line rounded-md px-3.5 py-2 hover:border-fr-line-strong hover:text-fr-ink transition-colors"
            >
              Export Market View
            </button>
            <button
              type="button"
              className="text-[12px] font-semibold text-fr-paper bg-fr-ink rounded-md px-3.5 py-2 hover:bg-fr-ink-soft transition-colors"
            >
              Generate Market Brief
            </button>
          </div>
          <div className="w-[420px]">
            <SectorPressureKPIs sector={sector} />
          </div>
        </div>
      </header>

      <section className="grid grid-cols-[260px_1fr_320px] gap-5 items-stretch">
        <MarketSectorsList activeSlug={sector.slug} />

        <div className="rounded-lg border border-fr-line bg-fr-paper p-6 flex flex-col items-center">
          <div className="text-center mb-2">
            <div className="text-[15px] font-semibold text-fr-ink">{sector.label} Sector Friction Radar</div>
            <div className="text-[11px] text-fr-ink-mute mt-0.5">
              Aggregated pressure pattern across tracked {sector.label.toLowerCase()} companies.
            </div>
          </div>
          <div className="w-full max-w-[420px]">
            <FrictionRadar
              values={sector.radar}
              centerValue={sector.pressure}
              centerLabel="Pressure"
              dominantDim={sector.dominantDim}
            />
          </div>
        </div>

        <SectorInterpretation sector={sector} />
      </section>

      <section className="grid grid-cols-[260px_1fr] gap-5 items-start">
        <div className="rounded-lg border border-fr-line bg-fr-paper p-4">
          <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint mb-2">Navigation Logic</div>
          <div className="text-[12px] text-fr-ink-soft leading-relaxed">
            Macro market view identifies sectors under pressure. Company landscape ranks organizations. Company radar
            explains the pain. Drilldown provides evidence and recommended positioning.
          </div>
        </div>

        <CompaniesInSectorTable sector={sector} />
      </section>
    </div>
  );
}
