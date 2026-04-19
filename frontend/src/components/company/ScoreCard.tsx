import type { FrictionScore } from '../../types/scoring';
import { FrictionTypeBadge } from '../common/Badge';
import { getFrictionLevel } from '../../services/insightComposer';

interface Props {
  score: FrictionScore;
  verdictType?: 'preliminary' | 'final';
}

export function ScoreCard({ score, verdictType }: Props) {
  const frictionInfo = getFrictionLevel(score.total_score);

  const isWeakEvidence = verdictType === 'preliminary' || score.total_score === 0;

  return (
    <div className="space-y-4">
      {/* Friction Level - Plain English */}
      <div className="flex items-start gap-6 flex-wrap">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Overall assessment</p>
          <div className="flex items-center gap-3">
            <span className={`text-2xl font-bold ${
              score.total_score >= 6 ? 'text-red-600' : 
              score.total_score >= 3 ? 'text-yellow-600' : 
              'text-emerald-600'
            }`}>
              {isWeakEvidence ? 'Insufficient data' : frictionInfo.level}
            </span>
            <span className="text-sm text-gray-500">
              ({score.total_score.toFixed(1)} / 10)
            </span>
          </div>
        </div>
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What this means</p>
          <p className="text-sm text-gray-700 max-w-md">
            {isWeakEvidence 
              ? 'Not enough evidence to determine a clear friction pattern yet.'
              : frictionInfo.description
            }
          </p>
        </div>
      </div>

      {/* Main challenge - only show when evidence is not weak */}
      {!isWeakEvidence && (
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Primary challenge</p>
          <FrictionTypeBadge type={score.dominant_friction_type} size="md" />
        </div>
      )}

      {/* When computed */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Last analyzed</p>
        <p className="text-sm text-gray-600">
          {new Date(score.computed_at).toLocaleDateString()}
        </p>
      </div>

      {/* Open Positions Count */}
      {score.open_positions_count && score.open_positions_count > 0 && (
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Open positions</p>
          <p className="text-lg font-semibold text-blue-600">
            {score.open_positions_count.toLocaleString()} roles available
          </p>
        </div>
      )}
    </div>
  );
}