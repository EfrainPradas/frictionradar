import type { ScoringBreakdown, FrictionCategory } from '../../types/scoring';
import { FrictionTypeBadge } from '../common/Badge';

const CATEGORY_ORDER: FrictionCategory[] = [
  'reporting_fragmentation',
  'process_inefficiency',
  'tooling_inconsistency',
  'scaling_strain',
  'customer_experience_friction',
];

interface Props {
  breakdown: ScoringBreakdown;
  maxScore?: number;
}

export function BreakdownPanel({ breakdown, maxScore = 10 }: Props) {
  return (
    <div className="space-y-3">
      {CATEGORY_ORDER.map((cat) => {
        const data = breakdown[cat];
        if (!data) return null;
        const pct = Math.min((data.score / maxScore) * 100, 100);

        return (
          <div key={cat} className="space-y-1.5">
            <div className="flex items-center justify-between gap-4">
              <FrictionTypeBadge type={cat} size="sm" />
              <span className="text-sm font-semibold text-gray-700 tabular-nums">
                {data.score.toFixed(2)}
              </span>
            </div>

            {/* Score bar */}
            <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-gray-400 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>

            {/* Matched signals */}
            {data.matched_signals.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {data.matched_signals.map((sig) => (
                  <span
                    key={sig}
                    className="text-xs bg-gray-100 text-gray-600 rounded px-2 py-0.5 font-mono"
                  >
                    {sig}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-400">No signals matched</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
