import { useQuery } from '@tanstack/react-query';
import { analysisService, type KpiLevel, type DiagnosticState, type CompanyEvaluation } from '../../services/analysis';

interface Props {
  companyId: string;
}

const KPI_LABELS: Record<keyof CompanyEvaluation['kpis'], string> = {
  extraction_coverage: 'Extraction Coverage',
  hiring_pressure: 'Hiring Pressure',
  function_concentration: 'Function Concentration',
  pain_clarity: 'Pain Clarity',
  company_type_confidence: 'Company Type Confidence',
  positioning_readiness: 'Positioning Readiness',
};

const KPI_ORDER: Array<keyof CompanyEvaluation['kpis']> = [
  'extraction_coverage',
  'hiring_pressure',
  'function_concentration',
  'pain_clarity',
  'company_type_confidence',
  'positioning_readiness',
];

const LEVEL_STYLES: Record<KpiLevel, string> = {
  high: 'bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20',
  moderate: 'bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/20',
  low: 'bg-white/5 text-gray-500 ring-1 ring-inset ring-white/10',
};

const DIAGNOSTIC_LABEL: Record<DiagnosticState, string> = {
  insufficient_evidence: 'Insufficient evidence',
  broad_hiring_pattern_detected: 'Broad hiring pattern detected',
  specific_pain_emerging: 'Specific pain emerging',
  specific_pain_identified: 'Specific pain identified',
  ready_for_positioning: 'Ready for positioning',
};

const DIAGNOSTIC_STYLES: Record<DiagnosticState, string> = {
  insufficient_evidence: 'bg-white/5 text-gray-500 ring-1 ring-inset ring-white/10',
  broad_hiring_pattern_detected: 'bg-sky-500/10 text-sky-400 ring-1 ring-inset ring-sky-500/20',
  specific_pain_emerging: 'bg-violet-500/10 text-violet-400 ring-1 ring-inset ring-violet-500/20',
  specific_pain_identified: 'bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/20',
  ready_for_positioning: 'bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20',
};

function LevelBadge({ level }: { level: KpiLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${LEVEL_STYLES[level]}`}
    >
      {level}
    </span>
  );
}

export function CompanyEvaluationScorecard({ companyId }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['company-evaluation', companyId],
    queryFn: () => analysisService.getCompanyEvaluation(companyId),
    enabled: !!companyId,
  });

  if (isLoading) {
    return <div className="text-sm text-gray-600">Loading evaluation…</div>;
  }

  if (error || !data) {
    return <div className="text-sm text-gray-600">Evaluation not available yet.</div>;
  }

  const diagnosticClass = DIAGNOSTIC_STYLES[data.diagnostic_state] ?? 'bg-white/5 text-gray-500 ring-1 ring-inset ring-white/10';
  const diagnosticLabel = DIAGNOSTIC_LABEL[data.diagnostic_state] ?? data.diagnostic_state;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${diagnosticClass}`}>
          {diagnosticLabel}
        </span>
        <span className="text-[10px] text-gray-600 uppercase tracking-wider">
          {data.evidence.open_positions_count > 0 && `${data.evidence.open_positions_count} open roles · `}
          {data.evidence.visible_hiring_areas} hiring areas · {data.evidence.distinct_signal_types} distinct signals
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {KPI_ORDER.map((key) => (
          <div key={key} className="flex items-center justify-between rounded border border-orbital-border bg-[#080b0e] px-3 py-2">
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">{KPI_LABELS[key]}</span>
            <LevelBadge level={data.kpis[key]} />
          </div>
        ))}
      </div>

      <div className="rounded border border-orbital-border bg-[#080b0e] px-3 py-2 text-sm text-gray-300 leading-relaxed">
        {data.summary}
      </div>

      {data.next_best_step && (
        <div className="text-xs text-gray-500">
          <span className="font-medium text-gray-400">Next best step: </span>
          {data.next_best_step}
        </div>
      )}

      {!data.allow_specific_pain_output && (
        <div className="text-xs text-amber-400/80">
          Specific-pain outputs are gated until Pain Clarity and Function Concentration both reach at least Moderate.
        </div>
      )}
    </div>
  );
}