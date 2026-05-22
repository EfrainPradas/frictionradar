import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCompanyDetail } from '../hooks/useCompanyDetail';
import { LoadingState, ErrorState, EmptyState } from '../components/common/States';
import { analysisService } from '../services/analysis';
import { Link } from 'react-router-dom';

export function ConsolePage() {
  // Use first company if no id in URL, or use :companyId param
  const { companyId } = useParams<{ companyId: string }>();

  const { data: companies } = useQuery({
    queryKey: ['companies'],
    queryFn: () => fetch('/api/companies').then(r => r.json()),
    staleTime: 60_000,
  });

  // If no companyId in URL, redirect to first company
  const targetId = companyId ?? (companies as any)?.[0]?.id;

  const {
    company,
    signals,
    latestScore,
    recalculateAll,
  } = useCompanyDetail(targetId ?? '');

  const { data: verdictData } = useQuery({
    queryKey: ['company-verdict', targetId],
    queryFn: () => analysisService.getCompanyVerdict(targetId!),
    enabled: !!targetId,
  });

  const { data: evaluationData } = useQuery({
    queryKey: ['company-evaluation', targetId],
    queryFn: () => analysisService.getCompanyEvaluation(targetId!),
    enabled: !!targetId,
  });

  const { data: temporalDiagnostic } = useQuery({
    queryKey: ['temporal-diagnostic', targetId],
    queryFn: () => fetch(`/api/temporal/${targetId}/diagnostic`).then(r => r.json()),
    enabled: !!targetId,
  });

  // Loading state
  if (!targetId) {
    return (
      <div className="flex h-screen" style={{ background: 'radial-gradient(circle at 72% 24%, rgba(215,180,106,0.13), transparent 30%), radial-gradient(circle at 20% 70%, rgba(120,185,143,0.08), transparent 34%), linear-gradient(135deg, #030404, #0b0f12 48%, #050607)' }}>
        <aside className="w-[82px] shrink-0 border-r border-[rgba(184,198,192,0.16)] bg-[rgba(5,6,7,0.78)] flex flex-col items-center py-6">
          <div className="w-[34px] h-[34px] rounded-full border border-[rgba(210,184,113,0.46)] relative mb-2" style={{ boxShadow: '0 0 24px rgba(215,180,106,.24)' }}>
            <div className="absolute inset-[7px] rounded-full border border-[rgba(215,180,106,.4)]" />
            <div className="absolute inset-[15px] rounded-full bg-[#d7b46a]" style={{ boxShadow: '0 0 18px #d7b46a' }} />
          </div>
        </aside>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-[#8e9994] font-mono text-[11px] tracking-[.18em] uppercase mb-4">Select a company from the Dashboard</div>
            <Link to="/dashboard" className="px-4 py-2 rounded-full border border-[rgba(210,184,113,0.46)] text-[11px] font-mono tracking-[.14em] uppercase text-[#d7b46a] bg-[rgba(215,180,106,0.08)] hover:bg-[rgba(215,180,106,0.16)] transition-colors">
              Go to Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (company.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: 'linear-gradient(135deg, #030404, #0b0f12 48%, #050607)' }}>
        <div className="text-center">
          <div className="w-10 h-10 rounded-full border border-[rgba(210,184,113,0.46)] mx-auto mb-4 animate-pulse" style={{ boxShadow: '0 0 24px rgba(215,180,106,.24)' }} />
          <div className="text-[#8e9994] font-mono text-[11px] tracking-[.18em] uppercase">Acquiring signals…</div>
        </div>
      </div>
    );
  }

  if (company.error || !company.data) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: 'linear-gradient(135deg, #030404, #0b0f12 48%, #050607)' }}>
        <ErrorState message={company.error?.message ?? 'Company not found'} />
      </div>
    );
  }

  const c = company.data;
  const signalData = signals.data ?? [];
  const score = latestScore.data;
  const verdict = verdictData?.final_verdict;
  const evaluation = evaluationData;
  const diagnostic = temporalDiagnostic as any;

  // ── Derived values ──────────────────────────────────────────
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

  const breakdown = score?.scoring_breakdown_json;
  const radarAxes = [
    { label: 'Pressure', value: totalScore ?? 0, max: 10 },
    { label: 'Velocity', value: diagnostic?.velocity_metrics?.signal_velocity_percent ?? 0, max: 100 },
    { label: 'Confidence', value: diagnostic?.confidence === 'high' ? 8 : diagnostic?.confidence === 'moderate' ? 5 : 2, max: 10 },
    { label: 'Readiness', value: evaluation?.allow_specific_pain_output ? 7 : 3, max: 10 },
    { label: 'Complexity', value: evaluation?.evidence?.distinct_signal_types ?? 0, max: 10 },
    { label: 'Coverage', value: Math.min((evaluation?.evidence?.visible_hiring_areas ?? 0) * 2, 10), max: 10 },
  ];

  const sparklineData = [22, 36, 32, 48, 42, 68, 86];

  const timelineEvents: { date: string; title: string; copy: string }[] = [];
  if (verdict) {
    timelineEvents.push({ date: 'Verdict', title: verdict.main_pain ?? 'Analysis complete', copy: verdict.where_pain_lives ?? '' });
  }
  if (score) {
    timelineEvents.push({ date: 'Scored', title: `Friction score: ${totalScore?.toFixed(1)}/10`, copy: `Dominant friction: ${frictionLabel[dominantFriction ?? ''] ?? 'Insufficient evidence'}` });
  }
  timelineEvents.push({ date: `${signalCount} signals`, title: 'Signal acquisition', copy: `Across ${new Set(signalData.map(s => s.signal_type)).size} distinct categories.` });

  const evidenceItems = signalData.slice(0, 4).map(s => ({
    source: s.signal_type?.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()).split(' ').slice(0, 2).join(' ') ?? 'Signal',
    strength: (s.confidence ?? 0) >= 0.8 ? 'High' : (s.confidence ?? 0) >= 0.5 ? 'Medium' : 'Low',
    text: s.signal_text,
  }));

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'radial-gradient(circle at 72% 24%, rgba(215,180,106,0.13), transparent 30%), radial-gradient(circle at 20% 70%, rgba(120,185,143,0.08), transparent 34%), linear-gradient(135deg, #030404, #0b0f12 48%, #050607)' }}>
      {/* Grid overlay */}
      <div className="fixed inset-0 pointer-events-none z-0" style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px)', backgroundSize: '44px 44px', maskImage: 'radial-gradient(circle at 50% 45%, black 0%, transparent 78%)' }} />
      {/* Scanlines */}
      <div className="fixed inset-0 pointer-events-none z-0" style={{ background: 'linear-gradient(to bottom, transparent 0%, rgba(255,255,255,.025) 50%, transparent 100%)', backgroundSize: '100% 7px', opacity: 0.18 }} />

      {/* Sidebar */}
      <aside className="w-[82px] shrink-0 flex flex-col items-center border-r border-[rgba(184,198,192,0.16)] bg-[rgba(5,6,7,0.78)] py-6 gap-[22px] relative z-10">
        <div className="w-[34px] h-[34px] rounded-full border border-[rgba(210,184,113,0.46)] relative mb-2" style={{ boxShadow: '0 0 24px rgba(215,180,106,.24)' }}>
          <div className="absolute inset-[7px] rounded-full border border-[rgba(215,180,106,.4)]" />
          <div className="absolute inset-[15px] rounded-full bg-[#d7b46a]" style={{ boxShadow: '0 0 18px #d7b46a' }} />
        </div>

        <nav className="flex-1 flex flex-col items-center gap-[14px]">
          <Link to="/dashboard" className="flex items-center justify-center w-10 h-10 rounded-[14px] border border-[rgba(184,198,192,0.16)] bg-[rgba(255,255,255,.03)] text-[#8e9994] hover:bg-[rgba(255,255,255,.06)] hover:text-[#edf2ef] transition-all group relative" title="Dashboard">
            FR
            <span className="absolute left-[52px] px-2 py-1 rounded bg-[#101418] border border-[rgba(184,198,192,0.16)] text-[11px] text-[#edf2ef] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">Dashboard</span>
          </Link>
          <div className="flex items-center justify-center w-10 h-10 rounded-[14px] border border-[rgba(210,184,113,0.46)] bg-[rgba(215,180,106,0.09)] text-[#d7b46a] shadow-[inset_0_0_18px_rgba(215,180,106,.09),0_0_24px_rgba(215,180,106,.11)] relative group" title="Console">
            CO
            <span className="absolute left-[52px] px-2 py-1 rounded bg-[#101418] border border-[rgba(184,198,192,0.16)] text-[11px] text-[#edf2ef] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">Console</span>
          </div>
          <Link to="/heatmap" className="flex items-center justify-center w-10 h-10 rounded-[14px] border border-[rgba(184,198,192,0.16)] bg-[rgba(255,255,255,.03)] text-[#8e9994] hover:bg-[rgba(255,255,255,.06)] hover:text-[#edf2ef] transition-all group relative" title="Heatmap">
            HM
            <span className="absolute left-[52px] px-2 py-1 rounded bg-[#101418] border border-[rgba(184,198,192,0.16)] text-[11px] text-[#edf2ef] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">Heatmap</span>
          </Link>
        </nav>
        <span className="text-[9px] text-[#59635f] font-mono">v2.0</span>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        {/* Topbar */}
        <header className="h-[76px] shrink-0 flex items-center justify-between px-7 border-b border-[rgba(184,198,192,0.16)] bg-[rgba(5,6,7,0.54)] backdrop-blur-[18px)]">
          <div className="flex items-center gap-4">
            <div>
              <div className="text-[13px] font-extrabold tracking-[.22em] uppercase text-[#edf2ef]">{c.name}</div>
              <div className="text-[11px] text-[#8e9994] font-mono mt-0.5">{c.domain ?? 'ORGANIZATIONAL INTELLIGENCE CONSOLE'}</div>
            </div>
          </div>
          <div className="flex items-center gap-[10px]">
            <div className="border border-[rgba(184,198,192,0.16)] px-[11px] py-2 rounded-full text-[11px] text-[#8e9994] font-mono bg-[rgba(255,255,255,.035)]">
              SIGNALS <strong className="text-[#d7b46a]">{signalCount}</strong>
            </div>
            <div className="border border-[rgba(184,198,192,0.16)] px-[11px] py-2 rounded-full text-[11px] text-[#8e9994] font-mono bg-[rgba(255,255,255,.035)]">
              CONFIDENCE <strong className="text-[#d7b46a]">{temporalConfidence === 'high' ? 'HIGH' : temporalConfidence === 'moderate' ? 'MOD' : 'LOW'}</strong>
            </div>
            <div className="border border-[rgba(184,198,192,0.16)] px-[11px] py-2 rounded-full text-[11px] text-[#8e9994] font-mono bg-[rgba(255,255,255,.035)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#78b98f] inline-block mr-1" style={{ boxShadow: '0 0 8px #78b98f', animation: 'orb-pulse 1.8s infinite' }} />
              LIVE
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-7 grid grid-cols-[1fr_370px] grid-rows-[auto_auto_auto] gap-[18px]" style={{ maxHeight: 'calc(100vh - 76px)' }}>
          {/* Hero Panel */}
          <div className="col-span-2 grid grid-cols-[1.3fr_0.9fr_0.9fr] gap-[18px]">
            {/* Company Card */}
            <div className="orb-panel animate-sheen p-6 flex flex-col justify-between">
              <div>
                <div className="font-mono text-[11px] tracking-[.18em] uppercase text-[#d7b46a]">Company Intelligence Profile</div>
                <div className="text-[38px] font-extrabold leading-none tracking-[-.04em] text-[#edf2ef] mt-2.5">{c.name}</div>
                <div className="text-[14px] text-[#8e9994] mt-2 max-w-[620px]">
                  {verdict?.main_pain
                    ? `Detected organizational pressure in ${verdict.where_pain_lives ?? 'operations'}. ${verdict.what_the_company_needs ?? ''}`
                    : (c.industry ?? 'Company') + ' — awaiting signal acquisition and friction analysis.'
                  }
                </div>
              </div>
              <div className="flex items-center gap-3 font-mono text-[11px] text-[#59635f]">
                <span className="w-2 h-2 rounded-full bg-[#78b98f]" style={{ boxShadow: '0 0 16px #78b98f', animation: 'orb-pulse 1.8s infinite' }} />
                {signalCount > 0 ? `${signalCount} SIGNALS ACQUIRED · ANALYSIS ACTIVE` : 'AWAITING SIGNAL ACQUISITION'}
              </div>
            </div>

            {/* Dominant Friction */}
            <div className="orb-panel animate-sheen p-5">
              <div className="font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">Dominant Friction</div>
              <div className="text-[42px] font-extrabold tracking-[-.04em] text-[#d7b46a] mt-2.5">
                {dominantFriction ? (frictionLabel[dominantFriction] ?? dominantFriction) : '—'}
              </div>
              <div className="text-[13px] text-[#8e9994] mt-1">
                {totalScore !== null ? `Score ${totalScore.toFixed(1)}/10` : 'No score yet'}
              </div>
              <div className="orb-tiny-bar mt-4">
                <span className="orb-tiny-bar-fill" style={{ width: totalScore !== null ? `${(totalScore / 10) * 100}%` : '0%' }} />
              </div>
            </div>

            {/* Temporal State */}
            <div className="orb-panel animate-sheen p-5">
              <div className="font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">Temporal State</div>
              <div className="text-[42px] font-extrabold tracking-[-.04em] text-[#78b98f] mt-2.5">
                {temporalLabel[temporalState] ?? 'Unknown'}
              </div>
              <div className="text-[13px] text-[#8e9994] mt-1">
                {temporalConfidence !== 'none' ? `Confidence: ${temporalConfidence}` : 'Awaiting temporal data'}
              </div>
              <div className="orb-tiny-bar mt-4">
                <span className="orb-tiny-bar-fill" style={{ width: temporalState === 'insufficient_temporal_data' ? '8%' : temporalState === 'emerging_pain' ? '55%' : temporalState === 'accelerating_pain' ? '78%' : '45%' }} />
              </div>
            </div>
          </div>

          {/* Radar + Timeline */}
          <div className="grid grid-cols-[1.08fr_0.92fr] gap-[18px] min-h-0">
            {/* Radar */}
            <div className="orb-panel animate-sheen p-[22px] flex flex-col">
              <div className="flex justify-between items-center font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994] mb-4">
                <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Organizational Radar</strong>
                <span>normalized score mesh</span>
              </div>
              <div className="flex-1 flex gap-[10px] min-h-0">
                <div className="flex-1 flex items-center justify-center">
                  <div className="relative w-[min(78%,460px)] aspect-square rounded-full border border-[rgba(215,180,106,.24)] flex items-center justify-center" style={{ boxShadow: 'inset 0 0 50px rgba(215,180,106,.05), 0 0 90px rgba(215,180,106,.08)' }}>
                    <div className="absolute inset-0 rounded-full animate-radar-sweep" style={{ background: 'conic-gradient(from 0deg, rgba(215,180,106,0), rgba(215,180,106,0.16), rgba(215,180,106,0) 52deg)' }} />
                    <div className="absolute rounded-full border border-[rgba(255,255,255,.07)]" style={{ inset: '12%' }} />
                    <div className="absolute rounded-full border border-[rgba(255,255,255,.07)]" style={{ inset: '26%' }} />
                    <div className="absolute rounded-full border border-[rgba(255,255,255,.07)]" style={{ inset: '40%' }} />
                    <div className="w-[58%] aspect-square animate-hex-breathe" style={{ clipPath: 'polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)', border: '1px solid #d7b46a', background: 'radial-gradient(circle, rgba(215,180,106,.18), rgba(215,180,106,.04) 52%, transparent 70%)', boxShadow: '0 0 40px rgba(215,180,106,.18)' }} />
                    {radarAxes.map((axis, i) => {
                      const positions = [
                        { top: '7%', left: '50%', transform: 'translateX(-50%)' },
                        { top: '28%', right: '3%' },
                        { bottom: '26%', right: '5%' },
                        { bottom: '7%', left: '50%', transform: 'translateX(-50%)' },
                        { bottom: '26%', left: '3%' },
                        { top: '28%', left: '3%' },
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

            {/* Timeline */}
            <div className="orb-panel animate-sheen p-[22px] flex flex-col">
              <div className="flex justify-between items-center font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994] mb-4">
                <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Temporal Intelligence</strong>
                <span>signal timeline</span>
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

          {/* Bottom Row */}
          <div className="grid grid-cols-3 gap-[18px]">
            <div className="orb-panel animate-sheen p-[18px]">
              <div className="flex justify-between items-center font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
                <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Signal Velocity</strong>
                <span>weekly</span>
              </div>
              <div className="orb-sparkline">
                {sparklineData.map((h, i) => (
                  <i key={i} className="orb-sparkline-bar" style={{ height: `${h}%` }} />
                ))}
              </div>
            </div>

            <div className="orb-panel animate-sheen p-[18px]">
              <div className="flex justify-between items-center font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
                <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Friction Deltas</strong>
                <span>category</span>
              </div>
              {radarAxes.filter(a => a.value > 0).slice(0, 2).map(axis => (
                <div key={axis.label} className="orb-readout mt-3">
                  <span className="orb-label">{axis.label}</span>
                  <strong className="orb-value text-[#edf2ef]">{axis.value.toFixed(1)} / 10</strong>
                </div>
              ))}
              {radarAxes.every(a => a.value === 0) && (
                <div className="orb-readout mt-3">
                  <span className="orb-label">Awaiting data</span>
                  <strong className="orb-value text-[#59635f]">No scores yet</strong>
                </div>
              )}
            </div>

            <div className="orb-panel animate-sheen p-[18px]">
              <div className="flex justify-between items-center font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
                <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Opportunity Lens</strong>
                <span>positioning</span>
              </div>
              <div className="orb-readout mt-3">
                <span className="orb-label">Recommended positioning</span>
                <strong className="orb-value text-[#edf2ef]">{verdict?.recommended_positioning ?? 'Awaiting analysis'}</strong>
              </div>
            </div>
          </div>

          {/* ── Right Panel ──────────────────────────────────────── */}
          <div className="row-start-2 col-start-2 row-end-4 border-l border-[rgba(184,198,192,0.16)] bg-[rgba(5,6,7,0.52)] backdrop-blur-[14px] p-6 overflow-auto flex flex-col gap-[18px]">
            {/* Verdict */}
            <div className="rounded-[24px] border border-[rgba(210,184,113,0.46)] p-[22px]" style={{ background: 'radial-gradient(circle at top right, rgba(215,180,106,.14), rgba(255,255,255,.03))', boxShadow: 'inset 0 0 40px rgba(215,180,106,.04)' }}>
              <div className="font-mono text-[11px] tracking-[.18em] uppercase text-[#d7b46a]">Temporal Verdict</div>
              <h2 className="text-[25px] leading-[1.04] tracking-[-.03em] font-extrabold text-[#edf2ef] mt-2.5">
                {verdict?.main_pain ?? 'Awaiting verdict generation.'}
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
              <div className="flex justify-between items-center font-mono text-[11px] tracking-[.14em] uppercase text-[#8e9994]">
                <strong className="text-[#edf2ef] font-sans text-[15px] tracking-normal normal-case">Evidence Chain</strong>
                <span>explainable</span>
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
              <div className="font-mono text-[11px] tracking-[.14em] uppercase text-[#78b98f]">Strategic Interpretation</div>
              <p className="text-[13px] text-[#8e9994] mt-2">
                {verdict?.what_the_company_needs
                  ? verdict.what_the_company_needs
                  : 'Awaiting verdict generation. Run analysis to unlock strategic recommendations.'
                }
              </p>
            </div>

            {/* Re-analyze button */}
            <button
              onClick={() => recalculateAll.mutate()}
              disabled={recalculateAll.isPending}
              className="w-full px-4 py-3 rounded-full border border-[rgba(210,184,113,0.46)] text-[11px] font-mono tracking-[.14em] uppercase text-[#d7b46a] bg-[rgba(215,180,106,0.08)] hover:bg-[rgba(215,180,106,0.16)] disabled:opacity-30 transition-colors"
            >
              {recalculateAll.isPending ? 'Analyzing…' : 'Re-analyze'}
            </button>
          </div>
        </main>
      </div>
    </div>
  );
}