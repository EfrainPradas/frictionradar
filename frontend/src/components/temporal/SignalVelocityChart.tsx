import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { PRESSURE_LABELS, PRESSURE_STYLES, CATEGORY_LABELS, BADGE_BASE } from './temporalConstants';
import type { PressureState, CategoryVelocity } from '../../types/temporal';
import type { FrictionCategory } from '../../types/scoring';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function SignalVelocityChart({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-velocity', companyId, lookbackDays],
    queryFn: () => temporalService.getVelocity(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Signal Velocity">
        <LoadingState label="Computing signal velocity…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Signal Velocity">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data || data.insufficient_data) {
    return (
      <SectionCard title="Signal Velocity">
        <div className="text-center py-6">
          <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3">
            <span className="text-gray-400 text-lg">—</span>
          </div>
          <p className="text-sm font-medium text-gray-600">No signal activity</p>
          <p className="text-xs text-gray-400 mt-1">
            No signals found in the {data?.window_days ?? lookbackDays}-day window.
          </p>
        </div>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="Signal Velocity">
      <div className="space-y-4">
        {/* Overall metrics */}
        <div className="grid grid-cols-2 gap-3">
          <MetricBox label="Total signals" value={String(data.total_signals)} />
          <MetricBox label="Scored" value={String(data.scored_signals)} sub={` / ${data.total_signals}`} />
          <MetricBox label="Velocity" value={data.overall_velocity.toFixed(1)} unit="signals/period" />
          <MetricBox label="Acceleration" value={data.overall_acceleration >= 0 ? `+${data.overall_acceleration.toFixed(2)}` : data.overall_acceleration.toFixed(2)} />
        </div>

        {/* Pressure badge */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 uppercase tracking-wide">Pressure</span>
          <span className={`${BADGE_BASE} ${PRESSURE_STYLES[data.overall_pressure as PressureState] ?? 'bg-gray-50 text-gray-700 ring-gray-200'}`}>
            {PRESSURE_LABELS[data.overall_pressure as PressureState] ?? data.overall_pressure}
          </span>
        </div>

        {/* Spike / drought alerts */}
        {(data.spike_detected || data.drought_detected) && (
          <div className="space-y-1.5">
            {data.spike_detected && (
              <div className="bg-amber-50 border border-amber-100 rounded px-3 py-2 text-xs text-amber-700">
                Signal spike detected{data.spike_bucket ? ` around ${new Date(data.spike_bucket).toLocaleDateString()}` : ''}
              </div>
            )}
            {data.drought_detected && (
              <div className="bg-gray-50 border border-gray-200 rounded px-3 py-2 text-xs text-gray-600">
                Signal drought: {data.drought_days} consecutive day{data.drought_days !== 1 ? 's' : ''} with no scored signals
              </div>
            )}
          </div>
        )}

        {/* Category velocities */}
        {data.category_velocities.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">By Category</p>
            <div className="space-y-2">
              {data.category_velocities.map((cv: CategoryVelocity) => (
                <div key={cv.category} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700">
                    {CATEGORY_LABELS[cv.category as FrictionCategory] ?? cv.category}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400">{cv.signal_count} signals</span>
                    <span className="font-medium text-gray-800">{cv.velocity.toFixed(1)}/period</span>
                    <span className={`text-xs ${cv.acceleration > 0 ? 'text-red-600' : cv.acceleration < 0 ? 'text-emerald-600' : 'text-gray-400'}`}>
                      {cv.acceleration > 0 ? '↑' : cv.acceleration < 0 ? '↓' : '→'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Source summary */}
        {data.source_summary.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Signal Sources</p>
            <div className="flex flex-wrap gap-2">
              {data.source_summary.map((s) => (
                <span key={s.source_type} className="text-xs bg-gray-50 border border-gray-100 rounded px-2 py-1 text-gray-600">
                  {s.source_type}: {s.signal_count}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Bucket bar chart */}
        {data.buckets.length > 0 && (
          <BucketChart buckets={data.buckets} />
        )}

        {/* Evidence */}
        {data.evidence && (
          <p className="text-xs text-gray-500 italic">{data.evidence}</p>
        )}
      </div>
    </SectionCard>
  );
}

function MetricBox({ label, value, sub, unit }: { label: string; value: string; sub?: string; unit?: string }) {
  return (
    <div className="bg-gray-50 border border-gray-100 rounded p-2">
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      <p className="text-lg font-semibold text-gray-800">
        {value}<span className="text-xs text-gray-400 font-normal">{sub}</span>
      </p>
      {unit && <p className="text-xs text-gray-400">{unit}</p>}
    </div>
  );
}

function BucketChart({ buckets }: { buckets: Array<{ bucket_start: string; total_count: number; scored_count: number; discovery_count: number }> }) {
  const maxCount = Math.max(...buckets.map(b => b.total_count), 1);

  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Activity Timeline</p>
      <div className="space-y-1">
        {buckets.map((b) => {
          const scoredPct = maxCount > 0 ? (b.scored_count / maxCount) * 100 : 0;
          const discoveryPct = maxCount > 0 ? (b.discovery_count / maxCount) * 100 : 0;
          const dateLabel = new Date(b.bucket_start).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

          return (
            <div key={b.bucket_start} className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-16 shrink-0">{dateLabel}</span>
              <div className="flex-1 flex items-center gap-px">
                <div
                  className="h-3 bg-blue-300 rounded-l"
                  style={{ width: `${Math.max(scoredPct, scoredPct > 0 ? 4 : 0)}%` }}
                  title={`Scored: ${b.scored_count}`}
                />
                <div
                  className="h-3 bg-gray-300 rounded-r"
                  style={{ width: `${Math.max(discoveryPct, discoveryPct > 0 ? 4 : 0)}%` }}
                  title={`Discovery: ${b.discovery_count}`}
                />
              </div>
              <span className="text-xs text-gray-500 w-8 text-right">{b.total_count}</span>
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-blue-300" /> Scored</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-gray-300" /> Discovery</span>
      </div>
    </div>
  );
}