import type { TemporalDiagnosticState } from '../../types/temporal';
import { DIAGNOSTIC_DESCRIPTIONS } from './temporalConstants';

interface Props {
  diagnosticState: TemporalDiagnosticState;
  snapshotCount: number;
  signalCount: number;
  scoredSignalCount: number;
}

const STATE_LABELS: Record<TemporalDiagnosticState, string> = {
  insufficient_temporal_data: 'Insufficient data',
  stable_low_friction: 'Low & stable',
  stable_elevated_friction: 'Elevated & stable',
  emerging_pain: 'Pain emerging',
  accelerating_pain: 'Pain accelerating',
  declining_pain: 'Pain declining',
  volatile_friction: 'Volatile',
};

export function InsufficientTemporalData({
  diagnosticState,
  snapshotCount,
  signalCount,
  scoredSignalCount,
}: Props) {
  return (
    <div className="rounded border border-gray-200 bg-gray-50 p-6 text-center space-y-3">
      <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto">
        <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-gray-600">
        {STATE_LABELS[diagnosticState]}
      </p>
      <p className="text-xs text-gray-400 max-w-sm mx-auto">
        {DIAGNOSTIC_DESCRIPTIONS[diagnosticState]}
      </p>
      <div className="flex items-center justify-center gap-6 text-xs text-gray-400 pt-2">
        <span>{snapshotCount} score snapshot{snapshotCount !== 1 ? 's' : ''}</span>
        <span>{signalCount} signals</span>
        <span>{scoredSignalCount} scored</span>
      </div>
      <p className="text-xs text-gray-400 pt-1">
        Temporal analysis requires at least 2 score snapshots and scored signals over time.
      </p>
    </div>
  );
}