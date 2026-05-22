import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { TREND_LABELS, TREND_STYLES, TREND_ARROWS, MAGNITUDE_LABELS, CATEGORY_LABELS } from './temporalConstants';
import type { FrictionCategory } from '../../types/scoring';
import type { TrendDirection, Magnitude } from '../../types/temporal';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function ScoreDeltaSummary({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-deltas', companyId, lookbackDays],
    queryFn: () => temporalService.getDeltas(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Score Delta Summary">
        <LoadingState label="Loading deltas…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Score Delta Summary">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data || data.insufficient_data) {
    return (
      <SectionCard title="Score Delta Summary">
        <div className="text-center py-6">
          <p className="text-sm text-gray-500">
            {data
              ? `${data.snapshot_count} snapshot${data.snapshot_count !== 1 ? 's' : ''} — need at least 2 for deltas`
              : 'No delta data available'}
          </p>
        </div>
      </SectionCard>
    );
  }

  const overall = data.overall;

  return (
    <SectionCard title="Score Delta Summary">
      <div className="space-y-4">
        {/* Window info */}
        <p className="text-xs text-gray-400">
          Comparing scores over {data.lookback_days}-day window
          {data.current_computed_at && data.previous_computed_at && (
            <> · from {new Date(data.previous_computed_at).toLocaleDateString()} to {new Date(data.current_computed_at).toLocaleDateString()}</>
          )}
        </p>

        {/* Overall delta */}
        {overall && (
          <div className="bg-gray-50 border border-gray-100 rounded p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Overall Trend</span>
              <span className={`text-sm font-medium ${TREND_STYLES[overall.trend as TrendDirection] ?? 'text-gray-500'}`}>
                {TREND_ARROWS[overall.trend as TrendDirection] ?? '—'} {TREND_LABELS[overall.trend as TrendDirection] ?? overall.trend}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Delta</span>
              <span className="font-medium text-gray-800">
                {overall.delta >= 0 ? '+' : ''}{overall.delta.toFixed(2)}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Magnitude</span>
              <span className="text-gray-700">{MAGNITUDE_LABELS[overall.magnitude as Magnitude] ?? overall.magnitude}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Previous</span>
              <span className="text-gray-700">{overall.previous_total.toFixed(2)}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Current</span>
              <span className="text-gray-700">{overall.current_total.toFixed(2)}</span>
            </div>
            {overall.dominant_shift && (
              <p className="text-xs text-gray-400 pt-1 border-t border-gray-100">
                Largest shift: {CATEGORY_LABELS[overall.dominant_shift as FrictionCategory] ?? overall.dominant_shift}
              </p>
            )}
          </div>
        )}

        {/* Per-category summary table */}
        {data.category_deltas.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">By Category</p>
            <div className="space-y-1.5">
              {data.category_deltas.map((d) => {
                const trend = d.trend as TrendDirection;
                return (
                  <div key={d.category} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700">
                      {CATEGORY_LABELS[d.category as FrictionCategory] ?? d.category}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className={`font-medium ${TREND_STYLES[trend] ?? 'text-gray-500'}`}>
                        {d.delta >= 0 ? '+' : ''}{d.delta.toFixed(2)}
                      </span>
                      <span className={`text-xs ${TREND_STYLES[trend] ?? 'text-gray-400'}`}>
                        {TREND_ARROWS[trend]}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Snapshot count */}
        <p className="text-xs text-gray-400 text-right">
          Based on {data.snapshot_count} score snapshot{data.snapshot_count !== 1 ? 's' : ''}
        </p>
      </div>
    </SectionCard>
  );
}