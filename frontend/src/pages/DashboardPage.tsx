import { useState } from 'react';
import { useCompanies } from '../hooks/useCompanies';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';
import { AppLayout } from '../components/layout/AppLayout';
import { AnalysisForm } from '../components/dashboard/AnalysisForm';
import { CompanyTable } from '../components/dashboard/CompanyTable';
import { BulkReanalyzeButton } from '../components/dashboard/BulkReanalyzeButton';
import { JsonImport } from '../components/dashboard/JsonImport';
import { LoadingState, ErrorState, EmptyState } from '../components/common/States';
import { analysisService } from '../services/analysis';
import type { FrictionScore } from '../types/scoring';

interface CompanyStats {
  signalsCount: number;
  lastCollectedAt?: string;
  lastScoredAt?: string;
}

interface CompanyVerdict {
  company_type: string;
  analysis_mode: string;
  target_fit: string;
  company_type_reason: string;
  final_verdict: {
    main_pain: string;
    where_pain_lives: string;
    what_the_company_needs: string;
    best_attack_angle: string;
  };
}

interface DashboardStatsResponse {
  scores: Record<string, FrictionScore>;
  stats: Record<string, CompanyStats>;
}

export function DashboardPage() {
  const { data: companies, isLoading, error, refetch } = useCompanies();
  const [verdicts, setVerdicts] = useState<Record<string, CompanyVerdict>>({});

  const { data: dashboardStats, refetch: refetchStats } = useQuery<DashboardStatsResponse>({
    queryKey: ['dashboard-stats'],
    queryFn: () => apiClient.get<DashboardStatsResponse>('/dashboard/stats').then((r) => r.data),
    enabled: !!companies && companies.length > 0,
    staleTime: 60_000,
  });

  const latestScores: Record<string, FrictionScore | null> = dashboardStats?.scores ?? {};
  const companyStats: Record<string, CompanyStats> = dashboardStats?.stats ?? {};
  const analyzedIds = new Set(Object.keys(latestScores));

  const handleAnalysisComplete = async (companyId: string) => {
    try {
      const verdict = await analysisService.getCompanyVerdict(companyId);
      setVerdicts(prev => ({ ...prev, [companyId]: verdict }));
    } catch {
      // Continue without verdict
    }

    refetch();
    refetchStats();
  };

  if (isLoading) {
    return (
      <AppLayout title="Dashboard" subtitle="Company triage & signal overview">
        <LoadingState label="Loading companies…" />
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout title="Dashboard" subtitle="Company triage & signal overview">
        <ErrorState message={error.message} />
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Dashboard" subtitle="Company triage & signal overview">
      <div className="space-y-6">
        {/* Analysis Form at top */}
        <AnalysisForm onAnalysisComplete={handleAnalysisComplete} />

        {/* Companies list */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">Companies</h2>
            <span className="text-xs text-gray-400">{companies?.length ?? 0} total</span>
          </div>

          <div className="flex items-center gap-3">
            {companies && companies.length > 0 && (
              <BulkReanalyzeButton companies={companies} analyzedIds={analyzedIds} onDone={() => { refetch(); refetchStats(); }} />
            )}
            <JsonImport onImportComplete={() => { refetch(); refetchStats(); }} />
          </div>

          {!isLoading && !error && companies && companies.length > 0 && (
            <CompanyTable
              companies={companies}
              latestScores={latestScores}
              companyStats={companyStats}
              verdicts={verdicts}
            />
          )}

          {!isLoading && !error && (!companies || companies.length === 0) && (
            <EmptyState
              title="No companies yet"
              description="Use the form above to analyze a company."
            />
          )}
        </div>
      </div>
    </AppLayout>
  );
}
