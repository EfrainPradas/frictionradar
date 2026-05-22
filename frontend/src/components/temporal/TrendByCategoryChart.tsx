import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { CATEGORY_LABELS, CATEGORY_STYLES, TREND_LABELS, TREND_STYLES, TREND_ARROWS, MAGNITUDE_LABELS } from './temporalConstants';
import type { FrictionCategory } from '../../types/scoring';
import type { TrendDirection } from '../../types/temporal';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

function DeltaBar({ value, maxAbs }: { value: number; maxAbs: number }) {
  const pct = maxAbs > 0 ? Math.abs(value) / maxAbs * 100 : 0;
  const isPositive = value > 0;
  return (
    <div className="flex items-center gap-2 flex-1">
      {isPositive ? (
        <>
          <div className="w-1/2" />
          <div
            className="h-2 rounded-r bg-red-300"
            style={{ width: `${Math.max(pct, 2)}%` }}
          />
        </>
      ) : (
        <>
          <div
            className="h-2 rounded-l bg-emerald-300"
            style={{ width: `${Math.max(pct, 2)}%` }}
          />
          <div className="w-1/2" />
        </>
      )}
    </div>
  );
}

export function TrendByCategoryChart({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-deltas', companyId, lookbackDays],
    queryFn: () => temporalService.getDeltas(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Trend by Category">
        <LoadingState label="Loading deltas…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Trend by Category">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data || data.insufficient_data) {
    return (
      <SectionCard title="Trend by Category">
        <InsufficientDeltaData snapshotCount={data?.snapshot_count ?? 0} />
      </SectionCard>
    );
  }

  const deltas = data.category_deltas;
  if (deltas.length === 0) {
    return (
      <SectionCard title="Trend by Category">
        <p className="text-sm text-gray-500">No category deltas available.</p>
      </SectionCard>
    );
  }

  const maxAbs = Math.max(...deltas.map(d => Math.abs(d.delta)), 0.01);

  return (
    <SectionCard title="Trend by Category">
      <div className="space-y-3">
        {/* Legend */}
        <div className="flex items-center gap-4 text-xs text-gray-400 mb-2">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-emerald-300" /> Improving (↓)
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded bg-red-300" /> Worsening (↑)
          </span>
          <span className="text-gray-300">|</span>
          <span>Over last {data.lookback_days} days</span>
        </div>

        {/* Category rows */}
        {deltas.map((d) => {
          const cat = d.category as FrictionCategory;
          const label = CATEGORY_LABELS[cat] ?? d.category;
          const colorClasses = CATEGORY_STYLES[cat] ?? 'bg-gray-50 text-gray-700';
          const trend = d.trend as TrendDirection;

          return (
            <div key={d.category} className="group">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${colorClasses}`}>
                    {label}
                  </span>
                  <span className={`text-xs font-medium ${TREND_STYLES[trend] ?? 'text-gray-500'}`}>
                    {TREND_ARROWS[trend]} {TREND_LABELS[trend] ?? trend}
                  </span>
                </div>
                <div className="text-xs text-gray-500">
                  {d.delta >= 0 ? '+' : ''}{d.delta.toFixed(2)} · {MAGNITUDE_LABELS[d.magnitude] ?? d.magnitude}
                </div>
              </div>
              <div className="flex items-center">
                <DeltaBar value={d.delta} maxAbs={maxAbs} />
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>Previous: {d.previous_normalized.toFixed(2)}</span>
                <span>Current: {d.current_normalized.toFixed(2)}</span>
              </div>
            </div>
          );
        })}

        {/* Overall */}
        {data.overall && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">
                Overall {TREND_ARROWS[data.overall.trend as TrendDirection] ?? '—'} {TREND_LABELS[data.overall.trend as TrendDirection] ?? data.overall.trend}
              </span>
              <span className="text-sm text-gray-600">
                {data.overall.delta >= 0 ? '+' : ''}{data.overall.delta.toFixed(2)}
              </span>
            </div>
            {data.overall.dominant_shift && (
              <p className="text-xs text-gray-400 mt-1">
                Dominant shift: {CATEGORY_LABELS[data.overall.dominant_shift as FrictionCategory] ?? data.overall.dominant_shift}
              </p>
            )}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function InsufficientDeltaData({ snapshotCount }: { snapshotCount: number }) {
  return (
    <div className="text-center py-6">
      <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
        <span className="text-gray-400 text-lg">—</span>
      </div>
      <p className="text-sm font-medium text-gray-600">Insufficient score history</p>
      <p className="text-xs text-gray-400 mt-1 max-w-xs mx-auto">
        Trend analysis requires at least 2 score snapshots. Currently: {snapshotCount} snapshot{snapshotCount !== 1 ? 's' : ''}.
      </p>
    </div>
  );
}