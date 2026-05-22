import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { BADGE_BASE, DIAGNOSTIC_LABELS, DIAGNOSTIC_STYLES, CONFIDENCE_STYLES, TREND_LABELS, TREND_STYLES, TREND_ARROWS, CATEGORY_LABELS } from './temporalConstants';
import type { TemporalDiagnosticState, TemporalConfidence } from '../../types/temporal';
import type { FrictionCategory } from '../../types/scoring';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function StrategicInterpretation({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-verdict', companyId, lookbackDays],
    queryFn: () => temporalService.getVerdict(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Strategic Interpretation">
        <LoadingState label="Computing strategic interpretation…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Strategic Interpretation">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data) return null;

  return (
    <SectionCard title="Strategic Interpretation">
      <div className="space-y-4">
        {/* Temporal status + trend */}
        {data.temporal_status && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`${BADGE_BASE} ${DIAGNOSTIC_STYLES[data.temporal_status as TemporalDiagnosticState] ?? 'bg-gray-50 text-gray-700 ring-gray-200'}`}>
              {DIAGNOSTIC_LABELS[data.temporal_status as TemporalDiagnosticState] ?? data.temporal_status}
            </span>
            {data.trend_direction && (
              <span className={`text-sm font-medium ${TREND_STYLES[data.trend_direction as keyof typeof TREND_STYLES] ?? 'text-gray-500'}`}>
                {TREND_ARROWS[data.trend_direction as keyof typeof TREND_ARROWS] ?? '—'} {TREND_LABELS[data.trend_direction as keyof typeof TREND_LABELS] ?? data.trend_direction}
              </span>
            )}
            {data.temporal_confidence && (
              <span className={`${BADGE_BASE} ${CONFIDENCE_STYLES[data.temporal_confidence as TemporalConfidence] ?? 'bg-gray-50 text-gray-600 ring-gray-200'}`}>
                {data.temporal_confidence} confidence
              </span>
            )}
          </div>
        )}

        {/* What we know */}
        {data.what_we_know && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we know</p>
            <p className="text-sm text-gray-700">{data.what_we_know}</p>
          </div>
        )}

        {/* What we do not know yet */}
        {data.what_we_do_not_know_yet && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we do not know yet</p>
            <p className="text-sm text-gray-600">{data.what_we_do_not_know_yet}</p>
          </div>
        )}

        {/* Top accelerating pain */}
        {data.top_accelerating_pain && (
          <PainCard
            label="Top Accelerating Pain"
            pain={data.top_accelerating_pain}
            accentColor="red"
          />
        )}

        {/* Top declining pain */}
        {data.top_declining_pain && (
          <PainCard
            label="Top Declining Pain"
            pain={data.top_declining_pain}
            accentColor="green"
          />
        )}

        {/* Main pain / positioning (verdict fields) */}
        {data.main_pain && (
          <div>
            <p className="text-xs text-red-600 uppercase tracking-wide mb-1">Main Pain</p>
            <p className="text-sm text-gray-800">{data.main_pain}</p>
          </div>
        )}

        {data.where_pain_lives && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Where the pain lives</p>
            <p className="text-sm text-gray-700">{data.where_pain_lives}</p>
          </div>
        )}

        {data.what_the_company_needs && (
          <div className="bg-emerald-50 border border-emerald-100 rounded px-4 py-3">
            <p className="text-xs text-emerald-600 uppercase tracking-wide mb-1">What the company likely needs</p>
            <p className="text-sm text-gray-800">{data.what_the_company_needs}</p>
          </div>
        )}

        {data.recommended_positioning && (
          <div className="bg-blue-50 border border-blue-100 rounded px-4 py-3">
            <p className="text-xs text-blue-600 uppercase tracking-wide mb-1">Recommended positioning</p>
            <p className="text-sm text-gray-700">{data.recommended_positioning}</p>
          </div>
        )}

        {/* Next best step */}
        {data.next_best_step && (
          <div className="bg-amber-50 border border-amber-100 rounded px-4 py-3">
            <p className="text-xs text-amber-600 uppercase tracking-wide mb-1">Next best step</p>
            <p className="text-sm text-gray-700">{data.next_best_step}</p>
          </div>
        )}

        {/* Eligibility */}
        {data.eligibility && (
          <EligibilityBanner eligibility={data.eligibility} />
        )}

        {/* Temporal reasoning trace */}
        {data.temporal_reasoning_trace && data.temporal_reasoning_trace.length > 0 && (
          <details className="group">
            <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700 select-none">
              Show reasoning trace
            </summary>
            <ol className="mt-2 space-y-1 pl-4">
              {data.temporal_reasoning_trace.map((step, i) => (
                <li key={i} className="text-xs text-gray-500">
                  <span className="text-gray-400">{step.condition}</span>
                  <span className="text-gray-300 mx-1">→</span>
                  <span className="text-gray-600">{step.result}</span>
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </SectionCard>
  );
}

function PainCard({ label, pain, accentColor }: { label: string; pain: Record<string, unknown>; accentColor: 'red' | 'green' }) {
  const category = typeof pain.category === 'string' ? pain.category : '';
  const delta = typeof pain.delta === 'number' ? pain.delta : 0;
  const label2 = CATEGORY_LABELS[category as FrictionCategory] ?? category;

  const borderClass = accentColor === 'red' ? 'border-red-100 bg-red-50' : 'border-green-100 bg-green-50';
  const titleClass = accentColor === 'red' ? 'text-red-600' : 'text-green-600';

  return (
    <div className={`rounded border ${borderClass} p-3`}>
      <p className={`text-xs ${titleClass} uppercase tracking-wide mb-1`}>{label}</p>
      <p className="text-sm font-medium text-gray-800">{label2}</p>
      <p className="text-xs text-gray-500 mt-0.5">
        Delta: {delta >= 0 ? '+' : ''}{delta.toFixed(2)}
      </p>
    </div>
  );
}

function EligibilityBanner({ eligibility }: { eligibility: NonNullable<NonNullable<import('../../types/temporal').TemporalVerdictResponse>['eligibility']> }) {
  const isEligible = eligibility.eligible;
  const hasTemporal = eligibility.temporal_gate_passed === true;

  return (
    <div className={`rounded border p-3 ${isEligible ? 'border-emerald-100 bg-emerald-50' : hasTemporal ? 'border-amber-100 bg-amber-50' : 'border-gray-200 bg-gray-50'}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-sm font-medium ${isEligible ? 'text-emerald-800' : hasTemporal ? 'text-amber-800' : 'text-gray-700'}`}>
          {isEligible ? 'Positioning eligible' : hasTemporal ? 'Conditionally eligible (temporal)' : 'Not yet eligible'}
        </span>
        {eligibility.confidence_band && (
          <span className="text-xs text-gray-500">{eligibility.confidence_band} confidence</span>
        )}
      </div>
      <p className="text-xs text-gray-600">{eligibility.reason}</p>
      {hasTemporal && eligibility.temporal_reason && (
        <p className="text-xs text-amber-700 mt-1">
          Temporal: {eligibility.temporal_reason}
          {eligibility.temporal_opportunity_type && ` — ${eligibility.temporal_opportunity_type.replace(/_/g, ' ')}`}
        </p>
      )}
    </div>
  );
}