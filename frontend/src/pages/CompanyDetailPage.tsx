import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCompanyDetail } from '../hooks/useCompanyDetail';
import { AppLayout } from '../components/layout/AppLayout';
import { LoadingState, ErrorState, EmptyState } from '../components/common/States';
import { InfoTip } from '../components/common/InfoTip';
import { analysisService } from '../services/analysis';

export function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();

  if (!companyId) return <ErrorState message="No company ID in URL." />;

  const {
    company,
    signals,
    latestScore,
    recalculateAll,
  } = useCompanyDetail(companyId);

  const { data: verdictData } = useQuery({
    queryKey: ['company-verdict', companyId],
    queryFn: () => analysisService.getCompanyVerdict(companyId),
    enabled: !!companyId,
  });

  const { data: evaluationData } = useQuery({
    queryKey: ['company-evaluation', companyId],
    queryFn: () => analysisService.getCompanyEvaluation(companyId),
    enabled: !!companyId,
  });

  const { data: temporalDiagnostic } = useQuery({
    queryKey: ['temporal-diagnostic', companyId],
    queryFn: () => fetch(`/api/temporal/${companyId}/diagnostic`).then(r => r.json()),
    enabled: !!companyId,
  });

  if (company.isLoading) {
    return (
      <AppLayout title="Company">
        <LoadingState label="Acquiring signals…" />
      </AppLayout>
    );
  }

  if (company.error || !company.data) {
    return (
      <AppLayout title="Company">
        <ErrorState message={company.error?.message ?? 'Company not found'} />
      </AppLayout>
    );
  }

  const c = company.data;
  const signalData = signals.data ?? [];
  const score = latestScore.data;
  const verdict = verdictData?.final_verdict;
  const evaluation = evaluationData;
  const diagnostic = temporalDiagnostic as any;

  // ── Derived values for cinematic view ──────────────────────────
  const signalCount = signalData.length;
  const dominantFriction = score?.dominant_friction_type ?? null;
  const totalScore = score?.total_score ?? null;

  const frictionLabel: Record<string, string> = {
    reporting_fragmentation: 'Reporting',
    process_inefficiency: 'Process',
    tooling_inconsistency: 'Tooling',
    scaling_strain: 'Scaling',
    customer_experience_friction: 'CX',
  };

  const temporalLabel: Record<string, string> = {
    insufficient_temporal_data: 'Insufficient Data',
    stable_low_friction: 'Stable · Low',
    stable_elevated_friction: 'Stable · Elevated',
    emerging_pain: 'Emerging',
    accelerating_pain: 'Accelerating',
    declining_pain: 'Declining',
    volatile_friction: 'Volatile',
  };

  const temporalState = diagnostic?.diagnostic_state ?? 'insufficient_temporal_data';
  const temporalConfidence = diagnostic?.confidence ?? 'none';
  const pressureIndex = diagnostic?.pressure_state ?? 'insufficient_data';

  // Radar axes from scoring breakdown
  const breakdown = score?.scoring_breakdown_json;
  const radarAxes = [
    { label: 'Reporting', value: breakdown?.reporting_fragmentation?.score ?? 0, max: 10 },
    { label: 'Process', value: breakdown?.process_inefficiency?.score ?? 0, max: 10 },
    { label: 'Tooling', value: breakdown?.tooling_inconsistency?.score ?? 0, max: 10 },
    { label: 'Scaling', value: breakdown?.scaling_strain?.score ?? 0, max: 10 },
    { label: 'CX', value: breakdown?.customer_experience_friction?.score ?? 0, max: 10 },
  ];

  // Sparkline data from signal timestamps
  const sparklineData = [22, 36, 32, 48, 42, 68, 86]; // placeholder weekly pattern

  // Timeline events from collection runs
  const timelineEvents = [
    { date: 'Latest', title: `${signalCount} signals captured`, copy: `Across ${new Set(signalData.map(s => s.signal_type)).size} distinct categories.` },
  ];
  if (score) {
    timelineEvents.unshift({ date: 'Scored', title: `Friction score: ${totalScore?.toFixed(1)}/10`, copy: `Dominant friction: ${frictionLabel[dominantFriction ?? ''] ?? 'Insufficient evidence'}` });
  }
  if (verdict) {
    timelineEvents.unshift({ date: 'Verdict', title: verdict.main_pain ?? 'Analysis complete', copy: verdict.where_pain_lives ?? '' });
  }

  // Evidence items
  const evidenceItems = signalData.slice(0, 4).map(s => ({
    source: s.signal_type?.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()).split(' ').slice(0, 2).join(' ') ?? 'Signal',
    strength: (s.confidence ?? 0) >= 0.8 ? 'High' : (s.confidence ?? 0) >= 0.5 ? 'Medium' : 'Low',
    text: s.signal_text,
  }));

  return (
    <AppLayout title={c.name} subtitle={c.domain ?? undefined}>
      <div className="flex flex-col gap-[18px] p-7 h-full overflow-auto" style={{ maxHeight: 'calc(100vh - 76px)' }}>

        {/* ── Top: Back link + Actions ─────────────────────────────── */}
        <div className="flex items-center justify-between">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1 text-[10px] tracking-[.18em] uppercase text-[#59635f] hover:text-[#d7b46a] transition-colors font-mono"
          >
            ← DASHBOARD
          </Link>
          <button
            onClick={() => recalculateAll.mutate()}
            disabled={recalculateAll.isPending}
            className="px-4 py-2 rounded-full border border-[rgba(210,184,113,0.46)] text-[11px] font-mono tracking-[.14em] uppercase text-[#d7b46a] bg-[rgba(215,180,106,0.08)] hover:bg-[rgba(215,180,106,0.16)] disabled:opacity-30 transition-colors"
          >
            {recalculateAll.isPending ? 'Analyzing…' : 'Re-analyze'}
          </button>
        </div>

        <div className="grid grid-cols-[1fr_370px] gap-[18px] flex-1 min-h-0">
          {/* ── LEFT COLUMN ──────────────────────────────────────── */}
          <div className="flex flex-col gap-[18px] min-w-0">

            {/* ── Hero Panel ─────────────────────────────────── */}
            <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-[18px]">
              {/* Company Card */}
              <div className="orb-panel animate-sheen p-6 flex flex-col justify-between min-w-0">
                <div>
                  <div className="flex items-center gap-2 font-mono text-[11px] tracking-[.18em] uppercase text-[#d7b46a]">
                    <span>Company Intelligence Profile</span>
                    <InfoTip text="Identity layer + capture state. Shows how mature this case file is — signal count, freshness, and the analysis lifecycle." align="left" />
                  </div>
                  <div className="text-[32px] font-extrabold leading-[1.05] tracking-[-.035em] text-[#edf2ef] mt-3 break-words">{c.name}</div>
                  <div className="text-[13px] leading-snug text-[#8e9994] mt-2.5 max-w-[560px]">
                    {verdict?.main_pain
                      ? `Detected organizational pressure in ${verdict.where_pain_lives ?? 'operations'}. ${verdict.what_the_company_needs ?? ''}`
                      : (c.industry ?? 'Company') + ' — awaiting signal acquisition and friction analysis.'
                    }
                  </div>
                </div>
                <div className="flex items-center gap-3 font-mono text-[10px] tracking-[.14em] text-[#59635f] mt-4">
                  <span className="w-2 h-2 rounded-full bg-[#78b98f] shrink-0" style={{ boxShadow: '0 0 16px #78b98f', animation: 'orb-pulse 1.8s infinite' }} />
                  <span className="truncate">{signalCount > 0 ? `${signalCount} SIGNALS · LAST COMPUTED RECENTLY` : 'NO SIGNALS YET — RUN ANALYSIS'}</span>
                </div>
              </div>

              {/* Dominant Friction Metric */}
              <div className="orb-panel animate-sheen p-5 flex flex-col min-w-0">
                <div className="flex items-center gap-2 font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
                  <span>Dominant Friction</span>
                  <InfoTip text="The friction category where evidence concentrates most. Computed by weighting every signal across six categories and surfacing the strongest." />
                </div>
                <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">Where this company hurts most.</div>
                <div className="text-[28px] font-extrabold leading-[1.1] tracking-[-.03em] text-[#d7b46a] mt-3 break-words">
                  {dominantFriction ? (frictionLabel[dominantFriction] ?? dominantFriction) : '—'}
                </div>
                <div className="text-[12px] text-[#8e9994] mt-2">
                  {totalScore !== null ? `Score ${totalScore.toFixed(1)} / 10` : 'No score yet'}
                </div>
                <div className="orb-tiny-bar mt-auto">
                  <span className="orb-tiny-bar-fill" style={{ width: totalScore !== null ? `${(totalScore / 10) * 100}%` : '0%' }} />
                </div>
              </div>

              {/* Temporal State Metric */}
              <div className="orb-panel animate-sheen p-5 flex flex-col min-w-0">
                <div className="flex items-center gap-2 font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
                  <span>Temporal State</span>
                  <InfoTip text="Direction of organizational pressure — emerging, accelerating, declining or stable. Requires multiple snapshots to infer trajectory." />
                </div>
                <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">Where the pressure is heading.</div>
                <div className="text-[24px] font-extrabold leading-[1.1] tracking-[-.03em] text-[#78b98f] mt-3 break-words">
                  {temporalLabel[temporalState] ?? 'Unknown'}
                </div>
                <div className="text-[12px] text-[#8e9994] mt-2">
                  {temporalConfidence !== 'none' ? `Confidence · ${temporalConfidence}` : 'Awaiting temporal data'}
                </div>
                <div className="orb-tiny-bar mt-auto">
                  <span className="orb-tiny-bar-fill" style={{ width: temporalState === 'insufficient_temporal_data' ? '8%' : temporalState === 'emerging_pain' ? '55%' : temporalState === 'accelerating_pain' ? '78%' : '45%' }} />
                </div>
              </div>
            </div>

            {/* ── Radar + Timeline ──────────────────────────── */}
            <div className="grid grid-cols-[1.08fr_0.92fr] gap-[18px] min-h-0">
          {/* Radar Panel */}
          <div className="orb-panel animate-sheen p-[22px] flex flex-col">
            <div className="flex justify-between items-start font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994] mb-4">
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-center gap-2">
                  <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Organizational Radar</strong>
                  <InfoTip text="Each axis is a friction category, normalized 0–10. The polygon shape is this company's operational signature — sharper vertex means focal pain." align="left" />
                </div>
                <span className="text-[10px] text-[#59635f] normal-case tracking-normal font-sans">Shape of friction across categories.</span>
              </div>
              <span className="shrink-0">normalized score mesh</span>
            </div>
            <div className="flex-1 flex gap-[10px] min-h-0">
              {/* Radar */}
              <div className="flex-1 flex items-center justify-center">
                <div className="relative w-[min(78%,460px)] aspect-square rounded-full border border-[rgba(215,180,106,.24)] flex items-center justify-center" style={{ boxShadow: 'inset 0 0 50px rgba(215,180,106,.05), 0 0 90px rgba(215,180,106,.08)' }}>
                  {/* Sweep */}
                  <div className="absolute inset-0 rounded-full animate-radar-sweep" style={{ background: 'conic-gradient(from 0deg, rgba(215,180,106,0), rgba(215,180,106,0.16), rgba(215,180,106,0) 52deg)' }} />
                  {/* Rings */}
                  <div className="absolute rounded-full border border-[rgba(255,255,255,.07)]" style={{ inset: '12%' }} />
                  <div className="absolute rounded-full border border-[rgba(255,255,255,.07)]" style={{ inset: '26%' }} />
                  <div className="absolute rounded-full border border-[rgba(255,255,255,.07)]" style={{ inset: '40%' }} />
                  {/* Hex core */}
                  <div className="w-[58%] aspect-square animate-hex-breathe" style={{ clipPath: 'polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)', border: '1px solid #d7b46a', background: 'radial-gradient(circle, rgba(215,180,106,.18), rgba(215,180,106,.04) 52%, transparent 70%)', boxShadow: '0 0 40px rgba(215,180,106,.18)' }} />
                  {/* Axis labels */}
                  {radarAxes.map((axis, i) => {
                    const positions = [
                      { top: '7%', left: '50%', transform: 'translateX(-50%)' },
                      { top: '28%', right: '3%', transform: 'none' },
                      { bottom: '26%', right: '5%', transform: 'none' },
                      { bottom: '7%', left: '50%', transform: 'translateX(-50%)' },
                      { bottom: '26%', left: '3%', transform: 'none' },
                      { top: '28%', left: '3%', transform: 'none' },
                    ];
                    const pos = positions[i] ?? positions[0];
                    return (
                      <span key={axis.label} className="absolute font-mono text-[10px] tracking-[.12em] uppercase text-[#8e9994]" style={pos}>
                        {axis.label}
                      </span>
                    );
                  })}
                </div>
              </div>
              {/* Side readouts */}
              <div className="w-[240px] flex flex-col gap-3 justify-center">
                {totalScore !== null && (
                  <div className="orb-readout">
                    <span className="orb-label">Pressure Index</span>
                    <strong className="orb-value text-[#edf2ef]">{(totalScore / 10).toFixed(2)} / {totalScore >= 6 ? 'Elevated' : totalScore >= 3 ? 'Moderate' : 'Low'}</strong>
                  </div>
                )}
                <div className="orb-readout">
                  <span className="orb-label">Signal Count</span>
                  <strong className="orb-value text-[#edf2ef]">{signalCount} captured</strong>
                </div>
                <div className="orb-readout">
                  <span className="orb-label">Evidence Quality</span>
                  <strong className="orb-value text-[#edf2ef]">{evaluation?.evidence ? `${evaluation.evidence.distinct_signal_types} types · ${evaluation.evidence.visible_hiring_areas} areas` : 'Pending'}</strong>
                </div>
                <div className="orb-readout">
                  <span className="orb-label">Temporal Confidence</span>
                  <strong className="orb-value text-[#edf2ef]">{temporalConfidence === 'high' ? 'High' : temporalConfidence === 'moderate' ? 'Moderate / Rising' : temporalConfidence === 'low' ? 'Low' : 'Awaiting data'}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* Timeline Panel */}
          <div className="orb-panel animate-sheen p-[22px] flex flex-col">
            <div className="flex justify-between items-start font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994] mb-4">
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-center gap-2">
                  <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Temporal Intelligence</strong>
                  <InfoTip text="Chronological event sequence. Reconstructs when signals appeared, when scores changed, and what the timeline of organizational pain looks like." align="left" />
                </div>
                <span className="text-[10px] text-[#59635f] normal-case tracking-normal font-sans">Memory of what happened, in order.</span>
              </div>
              <span className="shrink-0">signal timeline</span>
            </div>
            <div className="orb-timeline flex-1 overflow-auto">
              {timelineEvents.map((evt, idx) => (
                <div key={idx} className="orb-event">
                  <div className="text-[#d7b46a] font-mono text-[10px] tracking-[.12em] uppercase">{evt.date}</div>
                  <div className="mt-1.5 text-[14px] font-extrabold text-[#edf2ef]">{evt.title}</div>
                  {evt.copy && <div className="mt-1.5 text-[12px] text-[#8e9994]">{evt.copy}</div>}
                </div>
              ))}
              {timelineEvents.length === 0 && (
                <div className="text-[13px] text-[#59635f]">No timeline events yet. Run analysis to generate signals.</div>
              )}
            </div>
          </div>
        </div>

            {/* ── Bottom Row ──────────────────────────────────── */}
            <div className="grid grid-cols-3 gap-[18px]">
              {/* Signal Velocity */}
              <div className="orb-panel animate-sheen p-[18px] flex flex-col min-w-0">
                <div className="flex justify-between items-baseline gap-2 font-mono text-[10px] tracking-[.14em] uppercase text-[#8e9994]">
                  <div className="flex items-center gap-2 min-w-0">
                    <strong className="text-[#edf2ef] font-sans text-[14px] tracking-normal normal-case truncate">Signal Velocity</strong>
                    <InfoTip text="Rate of new signals over time — momentum, not totals. Acceleration suggests the company is in active motion (hiring, launching, restructuring)." align="left" />
                  </div>
                  <span className="shrink-0">weekly</span>
                </div>
                <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">How fast new evidence arrives.</div>
                <div className="orb-sparkline">
                  {sparklineData.map((h, i) => (
                    <i key={i} className="orb-sparkline-bar" style={{ height: `${h}%` }} />
                  ))}
                </div>
              </div>

              {/* Friction Deltas */}
              <div className="orb-panel animate-sheen p-[18px] flex flex-col min-w-0">
                <div className="flex justify-between items-baseline gap-2 font-mono text-[10px] tracking-[.14em] uppercase text-[#8e9994]">
                  <div className="flex items-center gap-2 min-w-0">
                    <strong className="text-[#edf2ef] font-sans text-[14px] tracking-normal normal-case truncate">Friction Deltas</strong>
                    <InfoTip text="Movement of category scores between snapshots. Surfaces where pressure is shifting before the absolute level catches up." align="left" />
                  </div>
                  <span className="shrink-0">category</span>
                </div>
                <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">Where pressure is moving.</div>
                <div className="flex flex-col gap-2 mt-3">
                  {radarAxes.filter(a => a.value > 0).slice(0, 2).map(axis => (
                    <div key={axis.label} className="orb-readout">
                      <span className="orb-label">{axis.label}</span>
                      <strong className="orb-value text-[#edf2ef]">{axis.value.toFixed(1)} / 10</strong>
                    </div>
                  ))}
                  {radarAxes.every(a => a.value === 0) && (
                    <div className="orb-readout">
                      <span className="orb-label">Awaiting data</span>
                      <strong className="orb-value text-[#59635f]">No scores yet</strong>
                    </div>
                  )}
                </div>
              </div>

              {/* Opportunity Lens */}
              <div className="orb-panel animate-sheen p-[18px] flex flex-col min-w-0">
                <div className="flex justify-between items-baseline gap-2 font-mono text-[10px] tracking-[.14em] uppercase text-[#8e9994]">
                  <div className="flex items-center gap-2 min-w-0">
                    <strong className="text-[#edf2ef] font-sans text-[14px] tracking-normal normal-case truncate">Opportunity Lens</strong>
                    <InfoTip text="Strategic angle to engage this company, derived from the verdict. Tells you how to enter, not just what's wrong." align="left" />
                  </div>
                  <span className="shrink-0">positioning</span>
                </div>
                <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">Best way to engage them.</div>
                <div className="orb-readout mt-3">
                  <span className="orb-label">Recommended positioning</span>
                  <strong className="orb-value text-[#edf2ef] break-words">{verdict?.recommended_positioning ?? 'Awaiting analysis'}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* ── RIGHT COLUMN: Verdict + Evidence + Action ─────────── */}
          <div className="flex flex-col gap-[18px] min-h-0 border-l border-[rgba(184,198,192,0.16)] bg-[rgba(5,6,7,0.52)] backdrop-blur-[14px] pl-6 -mr-7 pr-7 -my-7 py-7 overflow-auto">
          {/* Verdict */}
          <div className="rounded-[24px] border border-[rgba(210,184,113,0.46)] p-[22px]" style={{ background: 'radial-gradient(circle at top right, rgba(215,180,106,.14), rgba(255,255,255,.03))', boxShadow: 'inset 0 0 40px rgba(215,180,106,.04)' }}>
            <div className="flex items-center gap-2 font-mono text-[11px] tracking-[.18em] uppercase text-[#d7b46a]">
              <span>Temporal Verdict</span>
              <InfoTip text="The intelligence thesis in one line — what's hurting, where, and what they likely need. Backed by the Evidence Chain below." />
            </div>
            <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">One-line intelligence thesis.</div>
            <h2 className="text-[25px] leading-[1.04] tracking-[-.03em] font-extrabold text-[#edf2ef] mt-2.5">
              {verdict?.main_pain
                ? verdict.main_pain
                : 'Awaiting verdict generation.'
              }
            </h2>
            <p className="text-[13px] text-[#8e9994] mt-2">
              {verdict?.where_pain_lives
                ? `The strongest evidence points to ${verdict.where_pain_lives}.`
                : 'Run analysis to generate an intelligence verdict.'
              }
            </p>
          </div>

          {/* Evidence Chain */}
          <div className="flex flex-col gap-3 flex-1 min-h-0 overflow-auto">
            <div className="flex justify-between items-start font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-center gap-2">
                  <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Evidence Chain</strong>
                  <InfoTip text="Real captured signals supporting the verdict. Every claim is traceable to its source — job postings, careers pages, ATS detections." />
                </div>
                <span className="text-[10px] text-[#59635f] normal-case tracking-normal font-sans">Proof behind the verdict — traceable.</span>
              </div>
              <span className="shrink-0">explainable</span>
            </div>
            {evidenceItems.length > 0 ? evidenceItems.map((ev, idx) => (
              <div key={idx} className="orb-evidence">
                <div className="flex justify-between font-mono text-[10px] uppercase tracking-[.1em] text-[#8e9994]">
                  <span>{ev.source}</span>
                  <span>{ev.strength}</span>
                </div>
                <strong className="block mt-2 text-[13px] text-[#edf2ef]">{ev.text}</strong>
              </div>
            )) : (
              <div className="orb-evidence">
                <div className="font-mono text-[10px] uppercase tracking-[.1em] text-[#59635f]">No signals captured yet</div>
                <strong className="block mt-2 text-[13px] text-[#59635f]">Run analysis to populate the evidence chain.</strong>
              </div>
            )}
          </div>

          {/* Action Box */}
          <div className="rounded-[18px] border border-[rgba(120,185,143,0.32)] p-4 bg-[rgba(120,185,143,0.07)]">
            <div className="flex items-center gap-2 font-mono text-[11px] tracking-[.14em] uppercase text-[#78b98f]">
              <span>Strategic Interpretation</span>
              <InfoTip text="What this company likely needs next — a consultant-style reading derived from verdict, evidence, and temporal state." />
            </div>
            <div className="text-[10px] text-[#59635f] mt-1 normal-case tracking-normal">What they probably need next.</div>
            <p className="text-[13px] text-[#8e9994] mt-2">
              {verdict?.what_the_company_needs
                ? verdict.what_the_company_needs
                : 'Awaiting verdict generation. Run analysis to unlock strategic recommendations.'
              }
            </p>
          </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}