import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { SectionCard, LoadingState, ErrorState } from '../common/States';
import { CATEGORY_LABELS } from './temporalConstants';
import type { FrictionCategory } from '../../types/scoring';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function EvidenceTimeline({ companyId, lookbackDays = 30 }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['temporal-velocity', companyId, lookbackDays],
    queryFn: () => temporalService.getVelocity(companyId, lookbackDays),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <SectionCard title="Evidence Timeline">
        <LoadingState label="Loading timeline…" />
      </SectionCard>
    );
  }

  if (error) {
    return (
      <SectionCard title="Evidence Timeline">
        <ErrorState message={error.message} />
      </SectionCard>
    );
  }

  if (!data || data.insufficient_data || data.buckets.length === 0) {
    return null; // Don't show the section if no data
  }

  const buckets = data.buckets;

  return (
    <SectionCard title="Evidence Timeline">
      <div className="space-y-3">
        <p className="text-xs text-gray-400">
          Signal activity over the past {data.window_days} days ({buckets.length} period{buckets.length !== 1 ? 's' : ''})
        </p>

        {/* Timeline */}
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-3 top-2 bottom-2 w-px bg-gray-200" />

          <div className="space-y-0">
            {buckets.map((bucket, i) => {
              const date = new Date(bucket.bucket_start);
              const dateLabel = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
              const isLast = i === buckets.length - 1;
              const categories = Object.entries(bucket.category_counts)
                .filter(([, count]) => count > 0)
                .sort(([, a], [, b]) => b - a);

              return (
                <div key={bucket.bucket_start} className="flex gap-3 pb-3">
                  {/* Dot */}
                  <div className="relative z-10 mt-1.5">
                    <div className={`w-2 h-2 rounded-full ${bucket.total_count > 0 ? 'bg-blue-400' : 'bg-gray-300'}`} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs font-medium text-gray-600">{dateLabel}</span>
                      <span className="text-xs text-gray-400">
                        {bucket.total_count} signal{bucket.total_count !== 1 ? 's' : ''}
                      </span>
                    </div>
                    {categories.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {categories.map(([cat, count]) => (
                          <span
                            key={cat}
                            className="text-xs bg-gray-50 border border-gray-100 rounded px-1.5 py-0.5 text-gray-600"
                          >
                            {CATEGORY_LABELS[cat as FrictionCategory] ?? cat}: {count}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Spike / drought notices */}
        {(data.spike_detected || data.drought_detected) && (
          <div className="space-y-1.5">
            {data.spike_detected && (
              <div className="flex items-center gap-2 text-xs">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-amber-700">Signal spike detected</span>
                {data.spike_bucket && (
                  <span className="text-gray-400">
                    ({new Date(data.spike_bucket).toLocaleDateString()})
                  </span>
                )}
              </div>
            )}
            {data.drought_detected && (
              <div className="flex items-center gap-2 text-xs">
                <span className="w-2 h-2 rounded-full bg-gray-400" />
                <span className="text-gray-600">
                  Signal drought: {data.drought_days} day{data.drought_days !== 1 ? 's' : ''} without scored signals
                </span>
              </div>
            )}
          </div>
        )}

        {/* Source summary */}
        {data.source_summary.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Sources</p>
            <div className="flex flex-wrap gap-2">
              {data.source_summary.map((s) => (
                <span key={s.source_type} className="text-xs bg-gray-50 border border-gray-100 rounded px-2 py-0.5 text-gray-600">
                  {s.source_type}: {s.signal_count}
                  {s.latest_signal_at && (
                    <span className="text-gray-400 ml-1">
                      ({new Date(s.latest_signal_at).toLocaleDateString()})
                    </span>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}