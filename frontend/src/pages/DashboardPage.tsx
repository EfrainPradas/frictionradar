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
    recommended_positioning: string;
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

  // ── Compute stats for header metrics ──────────────────────────
  const totalCompanies = companies?.length ?? 0;
  const analyzedCount = analyzedIds.size;
  const highFriction = Object.values(latestScores).filter(s => s && s.total_score >= 6).length;
  const totalSignals = Object.values(companyStats).reduce((sum, s) => sum + (s.signalsCount ?? 0), 0);

  if (isLoading) {
    return (
      <AppLayout title="Dashboard" subtitle="Company triage & signal overview">
        <LoadingState label="Acquiring signals…" />
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
      <div className="space-y-5">
        {/* ── Command Input ──────────────────────────────────────── */}
        <AnalysisForm onAnalysisComplete={handleAnalysisComplete} />

        {/* ── Status Metrics Bar ──────────────────────────────────── */}
        <div className="grid grid-cols-4 gap-px rounded-lg overflow-hidden border border-orbital-border">
          <div className="bg-[#0b0f12] px-4 py-3">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600">Companies</p>
            <p className="text-2xl font-mono font-bold text-gray-200 mt-0.5 animate-counter">{totalCompanies}</p>
          </div>
          <div className="bg-[#0b0f12] px-4 py-3">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600">Analyzed</p>
            <p className="text-2xl font-mono font-bold text-amber-400 mt-0.5 animate-counter">{analyzedCount}</p>
          </div>
          <div className="bg-[#0b0f12] px-4 py-3">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600">High Friction</p>
            <p className="text-2xl font-mono font-bold text-red-400 mt-0.5 animate-counter">{highFriction}</p>
          </div>
          <div className="bg-[#0b0f12] px-4 py-3">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-600">Signals</p>
            <p className="text-2xl font-mono font-bold text-gray-200 mt-0.5 animate-counter">{totalSignals.toLocaleString()}</p>
          </div>
        </div>

        {/* ── Actions Row ──────────────────────────────────────── */}
        <div className="flex items-center gap-3">
          {companies && companies.length > 0 && (
            <BulkReanalyzeButton companies={companies} analyzedIds={analyzedIds} onDone={() => { refetch(); refetchStats(); }} />
          )}
          <JsonImport onImportComplete={() => { refetch(); refetchStats(); }} />
        </div>

        {/* ── Company Intelligence Feed ───────────────────────────── */}
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
            description="Use the command input above to analyze a company."
          />
        )}
      </div>
    </AppLayout>
  );
}