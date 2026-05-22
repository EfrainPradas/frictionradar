import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { BADGE_BASE, DIAGNOSTIC_LABELS, DIAGNOSTIC_STYLES, DIAGNOSTIC_DESCRIPTIONS, CONFIDENCE_LABELS, CONFIDENCE_STYLES } from './temporalConstants';
import type { TemporalDiagnosticState, TemporalConfidence } from '../../types/temporal';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function TemporalStatusCard({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-diagnostic', companyId, lookbackDays],
    queryFn: () => temporalService.getDiagnostic(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Temporal Status">
        <LoadingState label="Analyzing temporal patterns…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Temporal Status">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data) return null;

  const state = data.temporal_state as TemporalDiagnosticState;
  const confidence = data.confidence as TemporalConfidence;

  if (data.insufficient_data) {
    return (
      <SectionCard title="Temporal Status">
        <div className="text-center py-8">
          <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
            <span className="text-gray-400 text-lg">—</span>
          </div>
          <p className="text-sm font-medium text-gray-600">Insufficient temporal data</p>
          <p className="text-xs text-gray-400 mt-1 max-w-xs mx-auto">
            {DIAGNOSTIC_DESCRIPTIONS.insufficient_temporal_data}
          </p>
          <div className="mt-3 flex items-center justify-center gap-4 text-xs text-gray-400">
            <span>{data.score_snapshot_count} score snapshots</span>
            <span>{data.signal_count} signals</span>
            <span>{data.scored_signal_count} scored</span>
          </div>
        </div>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="Temporal Status">
      <div className="space-y-4">
        {/* Primary state badge */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`${BADGE_BASE} ${DIAGNOSTIC_STYLES[state]}`}>
            {DIAGNOSTIC_LABELS[state]}
          </span>
          <span className={`${BADGE_BASE} ${CONFIDENCE_STYLES[confidence]}`}>
            {CONFIDENCE_LABELS[confidence]}
          </span>
        </div>

        {/* Description */}
        <p className="text-sm text-gray-700">{DIAGNOSTIC_DESCRIPTIONS[state]}</p>

        {/* Summary if available */}
        {data.summary && (
          <div className="bg-gray-50 border border-gray-100 rounded p-3">
            <p className="text-sm text-gray-700">{data.summary}</p>
          </div>
        )}

        {/* Data availability indicators */}
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${data.score_delta_available ? 'bg-emerald-400' : 'bg-gray-300'}`} />
            Score deltas
          </span>
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${data.velocity_available ? 'bg-emerald-400' : 'bg-gray-300'}`} />
            Signal velocity
          </span>
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${data.evaluation_available ? 'bg-emerald-400' : 'bg-gray-300'}`} />
            Evaluation
          </span>
          <span>{data.score_snapshot_count} snapshots</span>
          <span>{data.scored_signal_count} scored signals</span>
        </div>
      </div>
    </SectionCard>
  );
}