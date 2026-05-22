import { Link, Navigate, useParams } from 'react-router-dom';
import { getCompanyDetail, type CompanySignal as MockSignal } from '../../data/mockCompany';
import { FrictionRadar } from '../../components/v2/sector/FrictionRadar';
import { RADAR_DIMENSIONS } from '../../data/taxonomy';
import { ExecutiveInterpretation } from '../../components/v2/company/ExecutiveInterpretation';
import { PositioningRecommendationPanel } from '../../components/v2/positioning/PositioningRecommendationPanel';
import { useState, useEffect } from 'react';
import { getCompanyPainProfile, type CompanyPainProfile } from '../../services/intelligence';
import { signalsService } from '../../services/signals';
import type { CompanySignal as ApiSignal } from '../../types/signal';

type SignalKind = 'job' | 'leadership' | 'news' | 'investment' | 'tech';

const SIGNAL_BADGE: Record<SignalKind, { label: string; cls: string }> = {
  job: { label: 'Job', cls: 'text-blue-700 bg-blue-50 border-blue-200' },
  leadership: { label: 'Leadership', cls: 'text-violet-700 bg-violet-50 border-violet-200' },
  news: { label: 'News', cls: 'text-slate-700 bg-slate-50 border-slate-200' },
  investment: { label: 'Investment', cls: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  tech: { label: 'Tech', cls: 'text-amber-700 bg-amber-50 border-amber-200' },
};

function mapSignalKind(signalType: string): SignalKind {
  const t = signalType.toLowerCase();
  if (t.includes('hir') || t.includes('job') || t.includes('role') || t.includes('career') || t.includes('recruit') || t.includes('position')) return 'job';
  if (t.includes('leader') || t.includes('exec') || t.includes('director') || t.includes('vp') || t.includes('chief')) return 'leadership';
  if (t.includes('invest') || t.includes('fund') || t.includes('round') || t.includes('acquisition')) return 'investment';
  if (t.includes('tech') || t.includes('stack') || t.includes('tool') || t.includes('platform') || t.includes('engineer') || t.includes('data_science') || t.includes('ai')) return 'tech';
  return 'news';
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  careers_page: 'Careers Page',
  ats_board: 'ATS Board',
  newsroom: 'Newsroom',
  public_review: 'Public Review',
  funding_database: 'Funding Database',
  linkedin: 'LinkedIn',
  glassdoor: 'Glassdoor',
  crunchbase: 'Crunchbase',
  g2: 'G2 Reviews',
  techcrunch: 'TechCrunch',
  indeed: 'Indeed',
  company_website: 'Company Website',
  sec_filing: 'SEC Filing',
  press_release: 'Press Release',
};

function dimLabel(slug: string): string {
  return RADAR_DIMENSIONS.find((d) => d.slug === slug)?.label ?? slug;
}

export function CompanyDetailV2() {
  const { sector, companyId } = useParams();
  const [painProfile, setPainProfile] = useState<CompanyPainProfile | null>(null);
  const [realSignals, setRealSignals] = useState<ApiSignal[]>([]);

  useEffect(() => {
    if (companyId) {
      getCompanyPainProfile(companyId).then(setPainProfile).catch(() => {});
      signalsService.list(companyId).then(setRealSignals).catch(() => {});
    }
  }, [companyId]);

  if (!sector || !companyId) return <Navigate to="/markets" replace />;

  const c = getCompanyDetail(sector, companyId);
  if (!c) return <Navigate to={`/markets/${sector}`} replace />;

  const velSign = c.velocityPct >= 0 ? '+' : '';

  return (
    <div className="p-7 flex flex-col gap-5 max-w-[1280px] mx-auto">
      <header className="rounded-lg border border-fr-line bg-fr-paper p-6 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">
              Company Intelligence
            </span>
            <span className="text-fr-ink-faint">·</span>
            <Link to={`/markets/${sector}`} className="text-[11px] text-fr-gold hover:underline">
              {c.sectorLabel}
            </Link>
          </div>
          <h1 className="text-[26px] font-semibold text-fr-ink leading-tight">{c.name}</h1>
          <div className="text-[12px] text-fr-ink-mute mt-1.5">
            {c.hqLine} · {c.sizeBand}
          </div>
          <p className="text-[13px] text-fr-ink-soft mt-3 max-w-2xl leading-relaxed">
            Primary friction: <span className="font-semibold text-fr-ink">{c.primaryPainLabel}</span>.
            Evidence comes from {c.signals.length} observable signals across hiring, leadership and public sources.
          </p>
        </div>

        <div className="shrink-0 flex flex-col items-end gap-3">
          <div className="flex items-center gap-2">
            <button className="text-[12px] font-medium text-fr-ink-soft border border-fr-line rounded-md px-3.5 py-2 hover:border-fr-line-strong hover:text-fr-ink transition-colors">
              Add to Watchlist
            </button>
            <button className="text-[12px] font-semibold text-fr-paper bg-fr-ink rounded-md px-3.5 py-2 hover:bg-fr-ink-soft transition-colors">
              Generate Company Brief
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 w-[320px]">
            <KPI label="Pressure" value={c.pressure} hint={c.pressure >= 70 ? 'Elevated' : 'Manageable'} />
            <KPI label="Velocity" value={`${velSign}${c.velocityPct}%`} hint="Last 30 days" tone={c.velocityPct > 5 ? 'text-orange-600' : c.velocityPct < -5 ? 'text-emerald-600' : 'text-fr-ink'} />
          </div>
        </div>
      </header>

      <section className="grid grid-cols-[1fr_360px] gap-5 items-stretch">
        <div className="rounded-lg border border-fr-line bg-fr-paper p-6 flex flex-col items-center">
          <div className="text-center mb-2">
            <div className="text-[15px] font-semibold text-fr-ink">{c.name} Friction Radar</div>
            <div className="text-[11px] text-fr-ink-mute mt-0.5">
              Five-dimension pressure profile derived from public signals.
            </div>
          </div>
          <div className="w-full max-w-[440px]">
            <FrictionRadar
              values={c.radar}
              centerValue={c.pressure}
              centerLabel="Pressure"
              dominantDim={c.primaryPainDim}
            />
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5 text-[11px] text-fr-ink-mute">
            <span className="font-mono tracking-wide text-fr-ink-faint">Dominant:</span>
            <span className="px-2 py-0.5 rounded-full bg-fr-gold-tint text-fr-gold font-semibold">
              {dimLabel(c.primaryPainDim)}
            </span>
          </div>
        </div>

        <aside className="rounded-lg border border-fr-line bg-fr-paper p-5 flex flex-col">
          <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">
            Recommended Positioning
          </div>
          <div className="text-[17px] font-semibold text-fr-ink mt-1.5 leading-tight">
            {c.positioningAngle.title}
          </div>
          <p className="text-[12.5px] text-fr-ink-soft leading-relaxed mt-2">{c.positioningAngle.summary}</p>

          <ul className="mt-4 space-y-2.5">
            {c.positioningAngle.bullets.map((b, i) => (
              <li key={i} className="flex gap-2.5 text-[12px] text-fr-ink-soft leading-relaxed">
                <span className="shrink-0 mt-0.5 w-4 h-4 rounded bg-fr-gold-tint text-fr-gold text-[10px] font-bold flex items-center justify-center">
                  {i + 1}
                </span>
                <span>{b}</span>
              </li>
            ))}
          </ul>

          <div className="flex-1" />
          <button className="mt-5 w-full rounded-md border border-fr-line text-fr-ink-soft text-[12px] font-semibold py-2.5 hover:border-fr-line-strong hover:text-fr-ink transition-colors">
            Copy Positioning
          </button>
        </aside>
      </section>

      <section className="grid grid-cols-[1fr_1fr] gap-5 items-start">
        <ExecutiveInterpretation
          companyName={c.name}
          dimensions={RADAR_DIMENSIONS.map((d) => ({
            name: d.slug,
            label: d.label,
            value: (c.radar as Record<string, number>)[d.slug] ?? 0,
            recommendedPositioning: painProfile?.positioning_angle ?? undefined,
          }))}
          dominantDimension={c.primaryPainDim}
        />

        <PositioningRecommendationPanel
          data={{
            recommended_positioning: painProfile?.recommended_positioning ?? c.positioningAngle.title,
            candidate_archetype: painProfile?.candidate_archetype ?? null,
            positioning_angle: painProfile?.positioning_angle ?? c.positioningAngle.summary,
            resume_emphasis: painProfile?.resume_emphasis ?? [],
            networking_angle: painProfile?.networking_angle ?? null,
            interview_themes: painProfile?.interview_themes ?? [],
            confidence_band: painProfile?.confidence_band ?? null,
          }}
        />
      </section>

      <section className="grid grid-cols-[1fr_1fr] gap-5 items-start">
        <div className="rounded-lg border border-fr-line bg-fr-paper">
          <div className="px-5 py-4 border-b border-fr-line">
            <div className="text-[14px] font-semibold text-fr-ink">Key Signals</div>
            <div className="text-[11px] text-fr-ink-mute mt-0.5">
              Observable inputs feeding the {dimLabel(c.primaryPainDim).toLowerCase()} score.
            </div>
          </div>
          <ul className="divide-y divide-fr-line">
            {(realSignals.length > 0 ? realSignals.slice(0, 8).map((s) => {
              const kind = mapSignalKind(s.signal_type);
              const badge = SIGNAL_BADGE[kind];
              const daysAgo = s.captured_at
                ? Math.max(0, Math.round((Date.now() - new Date(s.captured_at).getTime()) / 86400000))
                : 0;
              return (
                <li key={s.id} className="px-5 py-3 flex items-start gap-3">
                  <span className={`shrink-0 inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.cls}`}>
                    {badge.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] text-fr-ink-soft leading-snug">{s.signal_text}</div>
                    <div className="text-[10px] font-mono tracking-wide text-fr-ink-faint mt-1">
                      {s.signal_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}{s.confidence ? ` · ${Math.round(s.confidence * 100)}%` : ''} · {daysAgo}d ago
                    </div>
                  </div>
                </li>
              );
            }) : c.signals.map((s, i) => {
              const badge = SIGNAL_BADGE[s.kind];
              return (
                <li key={i} className="px-5 py-3 flex items-start gap-3">
                  <span className={`shrink-0 inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.cls}`}>
                    {badge.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] text-fr-ink-soft leading-snug">{s.text}</div>
                    <div className="text-[10px] font-mono tracking-wide text-fr-ink-faint mt-1">
                      weight {s.weight} · {s.daysAgo}d ago
                    </div>
                  </div>
                </li>
              );
            }))}
          </ul>
        </div>

        <div className="rounded-lg border border-fr-line bg-fr-paper">
          <div className="px-5 py-4 border-b border-fr-line">
            <div className="text-[14px] font-semibold text-fr-ink">Evidence</div>
            <div className="text-[11px] text-fr-ink-mute mt-0.5">Public sources backing the signals above.</div>
          </div>
          <ul className="divide-y divide-fr-line">
            {(realSignals.length > 0 ? realSignals.filter((s) => s.source_url || s.signal_text).slice(0, 6).map((s) => {
              const kind = mapSignalKind(s.signal_type);
              const badge = SIGNAL_BADGE[kind];
              const sourceLabel = SOURCE_TYPE_LABELS[s.source_type] || s.source_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
              const dateStr = s.captured_at ? s.captured_at.slice(0, 10) : '';
              return (
                <li key={s.id} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.cls}`}>
                      {sourceLabel}
                    </span>
                    <span className="text-[10px] font-mono tracking-wide text-fr-ink-faint">{dateStr}</span>
                  </div>
                  <div className="text-[12px] text-fr-ink-soft leading-snug mt-1">{s.signal_text}</div>
                  {s.source_url && (
                    <a
                      href={s.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-fr-gold hover:underline mt-1.5 inline-block"
                    >
                      Open source →
                    </a>
                  )}
                </li>
              );
            }) : c.evidence.map((e, i) => (
              <li key={i} className="px-5 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[11.5px] font-semibold text-fr-ink">{e.source}</span>
                  <span className="text-[10px] font-mono tracking-wide text-fr-ink-faint">{e.observedAt}</span>
                </div>
                <div className="text-[12px] text-fr-ink-soft leading-snug mt-1">{e.excerpt}</div>
              </li>
            )))}
          </ul>
        </div>
      </section>
    </div>
  );
}

function KPI({ label, value, hint, tone }: { label: string; value: number | string; hint: string; tone?: string }) {
  return (
    <div className="rounded-md border border-fr-line bg-fr-paper-2 px-3.5 py-2.5">
      <div className="text-[10px] font-mono tracking-[0.12em] uppercase text-fr-ink-faint">{label}</div>
      <div className={`mt-0.5 text-[20px] font-semibold tabular-nums ${tone ?? 'text-fr-ink'}`}>{value}</div>
      <div className="text-[10px] text-fr-ink-mute">{hint}</div>
    </div>
  );
}
