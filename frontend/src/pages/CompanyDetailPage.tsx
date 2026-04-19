import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCompanyDetail } from '../hooks/useCompanyDetail';
import { AppLayout } from '../components/layout/AppLayout';
import { CompanySummary } from '../components/company/CompanySummary';
import { ActionPanel } from '../components/company/ActionPanel';
import { CompanyTypeCard } from '../components/company/CompanyTypeCard';
import { FinalVerdictCard } from '../components/company/FinalVerdictCard';
import { KeySignals } from '../components/company/KeySignals';
import { ScoreCard } from '../components/company/ScoreCard';
import { BreakdownPanel } from '../components/company/BreakdownPanel';
import { HypothesisCard } from '../components/company/HypothesisCard';
import { SignalsTable } from '../components/company/SignalsTable';
import { CollectionRunsTable } from '../components/company/CollectionRunsTable';
import { SectionCard, LoadingState, ErrorState, EmptyState } from '../components/common/States';
import { generateWhatsHappening } from '../services/insightComposer';
import { analysisService } from '../services/analysis';
import { HiringIntelligenceCard } from '../components/company/HiringIntelligenceCard';
import { CompanyEvaluationScorecard } from '../components/company/CompanyEvaluationScorecard';
import { BroadHiringReadCard } from '../components/company/BroadHiringReadCard';

export function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();

  if (!companyId) return <ErrorState message="No company ID in URL." />;

  const {
    company,
    signals,
    collectionRuns,
    latestScore,
    latestHypothesis,
    runCollection,
    recomputeScore,
    generateHypothesis,
    recalculateAll,
  } = useCompanyDetail(companyId);

  const { data: verdictData } = useQuery({
    queryKey: ['company-verdict', companyId],
    queryFn: () => analysisService.getCompanyVerdict(companyId),
    enabled: !!companyId,
  });

  const { data: evaluationData } = useQuery({
    queryKey: ['company-evaluation', companyId],
    queryFn: () => analysisService.getCompanyEvaluation(companyId),
    enabled: !!companyId,
  });

  if (company.isLoading) {
    return (
      <AppLayout title="Company">
        <LoadingState label="Loading company…" />
      </AppLayout>
    );
  }

  if (company.error || !company.data) {
    return (
      <AppLayout title="Company">
        <ErrorState message={company.error?.message ?? 'Company not found'} />
      </AppLayout>
    );
  }

  const c = company.data;
  const signalData = signals.data ?? [];
  const verdictType = verdictData?.final_verdict?.verdict_type as 'preliminary' | 'final' | undefined || 'final';

  // Scorecard is the source of truth. Gate everything pain-specific when
  // Pain Clarity, Function Concentration, or Positioning Readiness are low.
  const evaluation = evaluationData;
  const isGated = !!evaluation && (
    evaluation.kpis.pain_clarity === 'low'
    || evaluation.kpis.function_concentration === 'low'
    || evaluation.kpis.positioning_readiness === 'low'
  );
  
  // Generate analysis attempts summary
  const runCount = collectionRuns.data?.length ?? 0;
  const uniqueSignalCount = new Set(signalData.map(s => s.signal_text.toLowerCase())).size;
  const analysisAttemptsSummary = generateAnalysisAttemptsSummary(runCount, uniqueSignalCount, signalData[0]?.signal_text);

  return (
    <AppLayout title={c.name} subtitle={c.domain ?? undefined}>
      <div className="space-y-5 max-w-5xl">
        <Link
          to="/dashboard"
          className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          ← Back to Dashboard
        </Link>

        <SectionCard title="Company Summary">
          <CompanySummary company={c} />
        </SectionCard>

        <SectionCard title="Actions">
          <ActionPanel
            onRecalculate={() => recalculateAll.mutate()}
            isRecalculating={recalculateAll.isPending}
          />
          {recalculateAll.error && (
            <div className="mt-3">
              <ErrorState
                message={(recalculateAll.error as Error | null)?.message || 'Analysis failed'}
              />
            </div>
          )}
        </SectionCard>

        {/* Company Evaluation Scorecard */}
        <SectionCard title="Company Evaluation Scorecard">
          <CompanyEvaluationScorecard companyId={companyId} />
        </SectionCard>

        {/* Company Type */}
        <SectionCard title="Company Type">
          <CompanyTypeCard companyId={companyId} />
        </SectionCard>

        {/* Broad Hiring Read — shown when the scorecard gates pain-specific output */}
        {isGated && evaluation && (
          <SectionCard title="Broad Hiring Read">
            <BroadHiringReadCard evaluation={evaluation} />
          </SectionCard>
        )}

        {/* Final Verdict — only when scorecard allows pain-specific output */}
        {!isGated && (
          <SectionCard title={verdictType === 'preliminary' ? 'Preliminary Verdict' : 'Final Verdict'}>
            <FinalVerdictCard companyId={companyId} />
          </SectionCard>
        )}

        {/* What's happening — only when not gated */}
        {!isGated && signalData.length > 0 && latestScore.data && (
          <SectionCard title="What's happening">
            <div className="text-sm text-gray-700 leading-relaxed">
              {generateWhatsHappening(c.name, signalData.slice(0, 5).map(s => s.signal_text))}
            </div>
          </SectionCard>
        )}

        {/* Key Signals */}
        <SectionCard title="Key Signals">
          {signals.isLoading ? (
            <LoadingState label="Loading signals…" />
          ) : signalData.length > 0 ? (
            <KeySignals signals={signalData} limit={5} />
          ) : (
            <EmptyState
              title="No signals yet"
              description="Run collection to gather signals."
            />
          )}
        </SectionCard>

        {/* Hiring Intelligence */}
        <SectionCard title="Hiring Intelligence">
          <HiringIntelligenceCard companyId={companyId} evaluation={evaluation} />
        </SectionCard>

        {/* Opportunity Hypothesis — only when not gated */}
        {!isGated && (
          <SectionCard title={verdictType === 'preliminary' ? 'Preliminary Read' : 'Opportunity Hypothesis'}>
            {latestHypothesis.isLoading ? (
              <LoadingState label="Loading hypothesis…" />
            ) : latestHypothesis.data ? (
              <HypothesisCard
                hypothesis={latestHypothesis.data}
                signalCount={signalData.length}
                collectionRunCount={collectionRuns.data?.length ?? 0}
                signalTexts={signalData.slice(0, 5).map(s => s.signal_text)}
                verdictType={verdictType}
              />
            ) : (
              <EmptyState
                title="No hypothesis generated"
                description="Score first, then generate hypothesis."
              />
            )}
          </SectionCard>
        )}

        {/* Internal Diagnostic — collapsed by default, secondary only */}
        <SectionCard title="Internal Diagnostic">
          <p className="text-xs text-gray-500 mb-3">
            Secondary diagnostic only. The Company Evaluation Scorecard above is the source of truth.
          </p>
          <details className="group">
            <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-900 select-none">
              Show legacy Friction Score
            </summary>
            <div className="mt-4 space-y-4">
              {latestScore.isLoading ? (
                <LoadingState label="Loading score…" />
              ) : latestScore.data ? (
                <>
                  <ScoreCard score={latestScore.data} verdictType={verdictType} />
                  <BreakdownPanel
                    breakdown={latestScore.data.scoring_breakdown_json}
                    maxScore={latestScore.data.total_score || 10}
                  />
                </>
              ) : (
                <EmptyState
                  title="No score computed"
                  description="Click 'Recompute Score' to analyze signals."
                />
              )}
            </div>
          </details>
        </SectionCard>

        {/* All Signals */}
        <SectionCard
          title={`What we noticed${signalData.length > 0 ? ` (${signalData.length})` : ''}`}
        >
          {signals.isLoading ? (
            <LoadingState label="Loading signals…" />
          ) : signals.error ? (
            <ErrorState message={signals.error.message} />
          ) : (
            <SignalsTable signals={signalData} showDeduplicated={true} />
          )}
        </SectionCard>

        {/* Analysis Attempts */}
        <SectionCard
          title={`Analysis Attempts${collectionRuns.data ? ` (${collectionRuns.data.length})` : ''}`}
        >
          {collectionRuns.isLoading ? (
            <LoadingState label="Loading runs…" />
          ) : collectionRuns.error ? (
            <ErrorState message={collectionRuns.error.message} />
          ) : (
            <>
              {verdictType === 'preliminary' && (
                <p className="text-sm text-gray-600 mb-3 pb-3 border-b border-gray-100">
                  {analysisAttemptsSummary}
                </p>
              )}
              <CollectionRunsTable runs={collectionRuns.data ?? []} />
            </>
          )}
        </SectionCard>
      </div>
    </AppLayout>
  );
}

function generateAnalysisAttemptsSummary(runCount: number, uniqueSignalCount: number, firstSignal?: string): string {
  if (runCount === 0) {
    return 'No analysis attempts yet.';
  }
  
  if (uniqueSignalCount <= 1) {
    return `The system analyzed this company ${runCount} time${runCount > 1 ? 's' : ''}. So far, it has only found one consistent signal: ${firstSignal || 'an active web presence'}.`;
  }
  
  if (uniqueSignalCount <= 3) {
    return `Multiple analysis attempts found a small set of ${uniqueSignalCount} consistent signals across different sources.`;
  }
  
  return `Multiple analysis attempts found several consistent signals across different sources.`;
}