import { useQuery } from '@tanstack/react-query';
import { temporalService } from '../../services/temporal';
import { TemporalStatusCard } from './TemporalStatusCard';
import { TrendByCategoryChart } from './TrendByCategoryChart';
import { ScoreDeltaSummary } from './ScoreDeltaSummary';
import { SignalVelocityChart } from './SignalVelocityChart';
import { EmergingPainPanel } from './EmergingPainPanel';
import { DecliningPainPanel } from './DecliningPainPanel';
import { EvidenceTimeline } from './EvidenceTimeline';
import { InsufficientTemporalData } from './InsufficientTemporalData';
import { StrategicInterpretation } from './StrategicInterpretation';
import type { TemporalDiagnosticState } from '../../types/temporal';

interface Props {
  companyId: string;
  lookbackDays?: number;
}

export function TemporalDashboard({ companyId, lookbackDays = 30 }: Props) {
  const { data: diagnostic } = useQuery({
    queryKey: ['temporal-diagnostic', companyId, lookbackDays],
    queryFn: () => temporalService.getDiagnostic(companyId, lookbackDays),
    enabled: !!companyId,
  });

  const state = diagnostic?.temporal_state as TemporalDiagnosticState | undefined;
  const isInsufficient = state === 'insufficient_temporal_data' || state === undefined;

  return (
    <div className="space-y-5">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Temporal Intelligence
        </h2>
        {diagnostic && (
          <span className="text-xs text-gray-400">
            {lookbackDays}-day window · {diagnostic.score_snapshot_count} snapshots · {diagnostic.scored_signal_count} scored signals
          </span>
        )}
      </div>

      {/* Insufficient data state */}
      {isInsufficient && diagnostic && (
        <InsufficientTemporalData
          diagnosticState={diagnostic.temporal_state as TemporalDiagnosticState}
          snapshotCount={diagnostic.score_snapshot_count}
          signalCount={diagnostic.signal_count}
          scoredSignalCount={diagnostic.scored_signal_count}
        />
      )}

      {/* Main status — always show */}
      <TemporalStatusCard companyId={companyId} lookbackDays={lookbackDays} />

      {/* Only show detailed panels when we have sufficient data */}
      {!isInsufficient && (
        <>
          {/* Strategic interpretation — most important */}
          <StrategicInterpretation companyId={companyId} lookbackDays={lookbackDays} />

          {/* Emerging / Declining pain — contextual, only renders if state matches */}
          <EmergingPainPanel companyId={companyId} lookbackDays={lookbackDays} />
          <DecliningPainPanel companyId={companyId} lookbackDays={lookbackDays} />

          {/* Category trend visualization */}
          <TrendByCategoryChart companyId={companyId} lookbackDays={lookbackDays} />

          {/* Score delta summary */}
          <ScoreDeltaSummary companyId={companyId} lookbackDays={lookbackDays} />

          {/* Signal velocity */}
          <SignalVelocityChart companyId={companyId} lookbackDays={lookbackDays} />

          {/* Evidence timeline */}
          <EvidenceTimeline companyId={companyId} lookbackDays={lookbackDays} />
        </>
      )}
    </div>
  );
}