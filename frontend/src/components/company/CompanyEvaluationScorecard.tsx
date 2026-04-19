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
  high: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  moderate: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-gray-50 text-gray-600 border-gray-200',
};

const DIAGNOSTIC_LABEL: Record<DiagnosticState, string> = {
  insufficient_evidence: 'Insufficient evidence',
  broad_hiring_pattern_detected: 'Broad hiring pattern detected',
  specific_pain_emerging: 'Specific pain emerging',
  specific_pain_identified: 'Specific pain identified',
  ready_for_positioning: 'Ready for positioning',
};

const DIAGNOSTIC_STYLES: Record<DiagnosticState, string> = {
  insufficient_evidence: 'bg-gray-100 text-gray-700',
  broad_hiring_pattern_detected: 'bg-sky-50 text-sky-700',
  specific_pain_emerging: 'bg-indigo-50 text-indigo-700',
  specific_pain_identified: 'bg-violet-50 text-violet-700',
  ready_for_positioning: 'bg-emerald-50 text-emerald-700',
};

function LevelBadge({ level }: { level: KpiLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${LEVEL_STYLES[level]}`}
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
    return <div className="text-sm text-gray-500">Loading evaluation…</div>;
  }

  if (error || !data) {
    return <div className="text-sm text-gray-500">Evaluation not available yet.</div>;
  }

  const diagnosticClass = DIAGNOSTIC_STYLES[data.diagnostic_state] ?? 'bg-gray-100 text-gray-700';
  const diagnosticLabel = DIAGNOSTIC_LABEL[data.diagnostic_state] ?? data.diagnostic_state;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${diagnosticClass}`}>
          {diagnosticLabel}
        </span>
        <span className="text-xs text-gray-500">
          {data.evidence.open_positions_count > 0 && `${data.evidence.open_positions_count} open roles · `}
          {data.evidence.visible_hiring_areas} hiring areas · {data.evidence.distinct_signal_types} distinct signals
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {KPI_ORDER.map((key) => (
          <div key={key} className="flex items-center justify-between rounded border border-gray-100 px-3 py-2">
            <span className="text-xs text-gray-600">{KPI_LABELS[key]}</span>
            <LevelBadge level={data.kpis[key]} />
          </div>
        ))}
      </div>

      <div className="rounded border border-gray-100 bg-gray-50 px-3 py-2 text-sm text-gray-700 leading-relaxed">
        {data.summary}
      </div>

      {data.next_best_step && (
        <div className="text-xs text-gray-500">
          <span className="font-medium text-gray-600">Next best step: </span>
          {data.next_best_step}
        </div>
      )}

      {!data.allow_specific_pain_output && (
        <div className="text-xs text-amber-700">
          Specific-pain outputs are gated until Pain Clarity and Function Concentration both reach at least Moderate.
        </div>
      )}
    </div>
  );
}
