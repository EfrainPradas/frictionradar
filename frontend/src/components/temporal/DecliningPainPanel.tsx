import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { BADGE_BASE, DIAGNOSTIC_LABELS, DIAGNOSTIC_STYLES, CONFIDENCE_STYLES, CATEGORY_LABELS, TREND_LABELS, TREND_ARROWS } from './temporalConstants';
import type { TemporalDiagnosticState, TemporalConfidence, TrendDirection } from '../../types/temporal';
import type { FrictionCategory } from '../../types/scoring';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function DecliningPainPanel({ companyId, lookbackDays = 30 }: Props) {
  const { data: deltaData, isLoading: deltaLoading, error: deltaError } = useQuery({
    queryKey: ['temporal-deltas', companyId, lookbackDays],
    queryFn: () => temporalService.getDeltas(companyId, lookbackDays),
    enabled: !!companyId,
  });

  const { data: diagData, isLoading: diagLoading, error: diagError } = useQuery({
    queryKey: ['temporal-diagnostic', companyId, lookbackDays],
    queryFn: () => temporalService.getDiagnostic(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (deltaLoading || diagLoading) {
    return (
      <SectionCard title="Declining Pain">
        <LoadingState label="Analyzing…" />
      </SectionCard>
    );
  }

  if (deltaError) {
    return (
      <SectionCard title="Declining Pain">
        <ErrorState message={deltaError.message} />
      </SectionCard>
    );
  }

  if (diagError && !diagData) {
    return (
      <SectionCard title="Declining Pain">
        <ErrorState message={diagError.message} />
      </SectionCard>
    );
  }

  if (!diagData) return null;

  const state = diagData.temporal_state as TemporalDiagnosticState;

  // Only show for declining pain
  if (state !== 'declining_pain') {
    return null;
  }

  // Find improving categories from deltas
  const improvingCategories = (deltaData?.category_deltas ?? [])
    .filter(d => d.trend === 'improving')
    .sort((a, b) => a.delta - b.delta); // most improving first (most negative delta)

  return (
    <SectionCard title="Declining Pain">
      <div className="space-y-4">
        {/* Positive banner */}
        <div className="rounded border border-green-100 bg-green-50 px-4 py-3">
          <p className="text-sm font-medium text-green-800">
            Friction is declining. This company appears to be resolving operational pain.
          </p>
        </div>

        {/* State badge */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`${BADGE_BASE} ${DIAGNOSTIC_STYLES[state]}`}>
            {DIAGNOSTIC_LABELS[state]}
          </span>
          <span className={`${BADGE_BASE} ${CONFIDENCE_STYLES[diagData.confidence as TemporalConfidence]}`}>
            {diagData.confidence} confidence
          </span>
        </div>

        {/* Improving categories */}
        {improvingCategories.length > 0 ? (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Improving Areas</p>
            <div className="space-y-2">
              {improvingCategories.map((d) => (
                <div key={d.category} className="flex items-center justify-between bg-green-50 border border-green-100 rounded px-3 py-2">
                  <span className="text-sm text-green-800">
                    {CATEGORY_LABELS[d.category as FrictionCategory] ?? d.category}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-green-700">
                      {d.delta.toFixed(2)}
                    </span>
                    <span className="text-xs text-green-600">
                      {TREND_ARROWS[d.trend as TrendDirection]} {TREND_LABELS[d.trend as TrendDirection] ?? d.trend}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-500">
            No individual categories show clear improvement trends yet.
          </p>
        )}

        {/* Summary */}
        {diagData.summary && (
          <div className="bg-gray-50 border border-gray-100 rounded p-3">
            <p className="text-sm text-gray-700">{diagData.summary}</p>
          </div>
        )}
      </div>
    </SectionCard>
  );
}