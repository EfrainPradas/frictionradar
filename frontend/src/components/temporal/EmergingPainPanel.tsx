import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { BADGE_BASE, DIAGNOSTIC_LABELS, DIAGNOSTIC_STYLES, CATEGORY_LABELS, EVIDENCE_STYLES, CONFIDENCE_STYLES } from './temporalConstants';
import type { TemporalDiagnosticState, TemporalConfidence, EvidenceStrength, TopChangingCategory } from '../../types/temporal';
import type { FrictionCategory } from '../../types/scoring';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function EmergingPainPanel({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-diagnostic', companyId, lookbackDays],
    queryFn: () => temporalService.getDiagnostic(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Emerging Pain">
        <LoadingState label="Analyzing…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Emerging Pain">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data) return null;

  const state = data.temporal_state as TemporalDiagnosticState;

  // Only show this panel for emerging or accelerating pain
  if (state !== 'emerging_pain' && state !== 'accelerating_pain') {
    return null;
  }

  const isAccelerating = state === 'accelerating_pain';

  return (
    <SectionCard title={isAccelerating ? 'Accelerating Pain' : 'Emerging Pain'}>
      <div className="space-y-4">
        {/* Alert banner */}
        <div className={`rounded border px-4 py-3 ${isAccelerating ? 'bg-red-50 border-red-100' : 'bg-indigo-50 border-indigo-100'}`}>
          <p className={`text-sm font-medium ${isAccelerating ? 'text-red-800' : 'text-indigo-800'}`}>
            {isAccelerating
              ? 'Friction is accelerating rapidly. This company\'s operational pain is getting worse.'
              : 'Signs of friction are beginning to emerge that weren\'t present before.'}
          </p>
        </div>

        {/* State and confidence */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`${BADGE_BASE} ${DIAGNOSTIC_STYLES[state]}`}>
            {DIAGNOSTIC_LABELS[state]}
          </span>
          <span className={`${BADGE_BASE} ${CONFIDENCE_STYLES[data.confidence as TemporalConfidence]}`}>
            {data.confidence} confidence
          </span>
        </div>

        {/* Top changing category */}
        {data.top_changing_category && (
          <TopChangingCategoryCard category={data.top_changing_category} />
        )}

        {/* Reasoning trace */}
        {data.reasoning_trace.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Reasoning</p>
            <ol className="space-y-1.5">
              {data.reasoning_trace.map((step, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="text-gray-300 shrink-0">{i + 1}.</span>
                  <div>
                    <span className="text-gray-600">{step.condition}</span>
                    <span className="text-gray-400 mx-1">→</span>
                    <span className="text-gray-800">{step.result}</span>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        {/* Summary */}
        {data.summary && (
          <div className="bg-gray-50 border border-gray-100 rounded p-3">
            <p className="text-sm text-gray-700">{data.summary}</p>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function TopChangingCategoryCard({ category }: { category: TopChangingCategory }) {
  const label = CATEGORY_LABELS[category.category as FrictionCategory] ?? category.category;
  const evidenceStyle = EVIDENCE_STYLES[category.evidence_strength as EvidenceStrength] ?? 'bg-gray-50 text-gray-700 ring-gray-200';

  return (
    <div className="bg-gray-50 border border-gray-100 rounded p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-800">{label}</span>
        <span className={`${BADGE_BASE} ${evidenceStyle}`}>
          {category.evidence_strength} evidence
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div>
          <p className="text-xs text-gray-400">Delta</p>
          <p className="font-medium text-gray-800">{category.delta >= 0 ? '+' : ''}{category.delta.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Trend</p>
          <p className="font-medium text-gray-800 capitalize">{category.trend.replace('_', ' ')}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400">Velocity</p>
          <p className="font-medium text-gray-800">{category.velocity.toFixed(1)}/period</p>
        </div>
      </div>
    </div>
  );
}