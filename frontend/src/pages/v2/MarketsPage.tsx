import { useNavigate } from 'react-router-dom';
import { useUIStore } from '../../store/uiStore';
import { FrictionHeatmap } from '../../components/v2/heatmap/FrictionHeatmap';
import { HeatmapModeToggle } from '../../components/v2/heatmap/HeatmapModeToggle';
import { HeatmapLegend } from '../../components/v2/heatmap/HeatmapLegend';
import { HEATMAP_CELLS } from '../../data/mockHeatmap';
import { SECTORS, FUNCTIONS } from '../../data/taxonomy';
import { SECTOR_AGGREGATES, SECTOR_TAGLINE } from '../../data/mockSector';

function avg(nums: number[]): number {
  if (!nums.length) return 0;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

const MODE_COPY: Record<string, { title: string; sub: string }> = {
  intensity: {
    title: 'Pain Intensity',
    sub: 'Where the friction is most acute right now. Darker = more pain reported across signals.',
  },
  velocity: {
    title: 'Velocity',
    sub: 'How fast pain is changing. Orange = growing, green = easing, grey = stable.',
  },
  opportunity: {
    title: 'Opportunity',
    sub: 'Pain weighted by hiring spikes, leadership churn and buying intent. Gold = best fit.',
  },
};

export function MarketsPage() {
  const navigate = useNavigate();
  const { heatmapMode, setHeatmapMode } = useUIStore();
  const copy = MODE_COPY[heatmapMode];

  const avgIntensity = Math.round(avg(HEATMAP_CELLS.map((c) => c.intensity)));
  const accelerating = HEATMAP_CELLS.filter((c) => c.velocity > 0.4).length;
  const totalCompanies = SECTOR_AGGREGATES.reduce((s, c) => s + c.companiesTracked, 0);
  const topSectors = [...SECTOR_AGGREGATES].sort((a, b) => b.pressure - a.pressure).slice(0, 5);

  return (
    <div className="p-7 flex flex-col gap-6 max-w-[1400px] mx-auto">
      <header className="flex items-start justify-between gap-6">
        <div>
          <div className="text-[11px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint mb-1">Markets · Macro view</div>
          <h1 className="text-[26px] font-semibold text-fr-ink leading-tight">{copy.title}</h1>
          <p className="text-[13px] text-fr-ink-mute mt-1.5 max-w-2xl leading-relaxed">{copy.sub}</p>
        </div>
        <HeatmapModeToggle value={heatmapMode} onChange={setHeatmapMode} />
      </header>

      <section className="grid grid-cols-4 gap-4">
        <KPI label="Avg pain" value={avgIntensity} suffix="/100" hint="Mean intensity across all cells" />
        <KPI label="Accelerating cells" value={accelerating} suffix={` of ${HEATMAP_CELLS.length}`} hint="Cells with rising friction (velocity > 0.4)" />
        <KPI label="Companies tracked" value={totalCompanies} hint="Distinct companies in coverage" />
        <KPI label="Markets covered" value={SECTORS.length * FUNCTIONS.length} hint="Sectors × Functions" />
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-[14px] font-semibold text-fr-ink">Start here · Top sectors under pressure</div>
            <div className="text-[11.5px] text-fr-ink-mute mt-0.5">
              Click a card to open the sector friction radar and ranked companies.
            </div>
          </div>
          <button
            type="button"
            onClick={() => navigate('/markets/' + topSectors[0].slug)}
            className="text-[12px] font-semibold text-fr-paper bg-fr-ink rounded-md px-3.5 py-2 hover:bg-fr-ink-soft transition-colors"
          >
            Open top sector →
          </button>
        </div>

        <div className="grid grid-cols-5 gap-3">
          {topSectors.map((s, i) => (
            <button
              key={s.slug}
              type="button"
              onClick={() => navigate(`/markets/${s.slug}`)}
              className="text-left rounded-lg border border-fr-line bg-fr-paper p-4 hover:border-fr-gold-soft hover:shadow-md transition-all"
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-mono tracking-wide text-fr-ink-faint">#{i + 1}</span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-fr-gold-tint text-fr-gold">
                  {s.pressure}
                </span>
              </div>
              <div className="text-[13.5px] font-semibold text-fr-ink leading-tight mb-1">{s.label}</div>
              <div className="text-[11px] text-fr-ink-mute leading-snug line-clamp-2">
                {SECTOR_TAGLINE[s.slug] ?? '—'}
              </div>
              <div className="mt-2 flex items-center justify-between text-[10.5px] text-fr-ink-faint font-mono tracking-wide">
                <span>{s.companiesTracked} cos</span>
                <span className={s.velocityPct > 5 ? 'text-orange-600' : s.velocityPct < -5 ? 'text-emerald-600' : ''}>
                  {s.velocityPct >= 0 ? '+' : ''}{s.velocityPct}%
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[14px] font-semibold text-fr-ink">Detailed grid · Sector × Function</div>
            <div className="text-[11.5px] text-fr-ink-mute mt-0.5">
              Hover to inspect a cell · click anywhere to open that sector.
            </div>
          </div>
          <HeatmapLegend mode={heatmapMode} />
        </div>
        <FrictionHeatmap mode={heatmapMode} />
      </section>

      <section className="rounded-lg border border-fr-line bg-fr-paper-2 p-5">
        <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint mb-3">Navigation logic</div>
        <ol className="grid grid-cols-4 gap-4 text-[12px] text-fr-ink-soft">
          <Step n={1} title="Macro market" body="Identify sectors under pressure here." />
          <Step n={2} title="Sector radar" body="Open a sector to see its 5-dim friction profile and ranked companies." />
          <Step n={3} title="Company radar" body="Open a company to see its signals, evidence and positioning." />
          <Step n={4} title="Brief" body="Generate an executive brief at any level (market, sector, company)." />
        </ol>
      </section>
    </div>
  );
}

function KPI({ label, value, suffix, hint }: { label: string; value: number; suffix?: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-fr-line bg-fr-paper px-5 py-4">
      <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">{label}</div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span className="text-[24px] font-semibold text-fr-ink tabular-nums">{value}</span>
        {suffix && <span className="text-[12px] text-fr-ink-mute">{suffix}</span>}
      </div>
      {hint && <div className="text-[11px] text-fr-ink-mute mt-1 leading-snug">{hint}</div>}
    </div>
  );
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <li className="flex gap-3">
      <span className="shrink-0 w-6 h-6 rounded-full bg-fr-ink text-fr-paper text-[11px] font-bold flex items-center justify-center">
        {n}
      </span>
      <div>
        <div className="text-[12.5px] font-semibold text-fr-ink">{title}</div>
        <div className="text-[11.5px] text-fr-ink-mute leading-snug mt-0.5">{body}</div>
      </div>
    </li>
  );
}

