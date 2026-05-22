import { useQuery } from '@tanstack/react-query';
import { analysisService } from '../../services/analysis';

interface CompanyVerdict {
  company_type: string;
  analysis_mode: string;
  target_fit: string;
  company_type_confidence: string;
  company_type_reason: string;
  final_verdict: {
    main_pain: string;
    where_pain_lives: string;
    what_the_company_needs: string;
    recommended_positioning: string;
  };
}

interface Props {
  companyId: string;
}

export function CompanyTypeCard({ companyId }: Props) {
  const { data: verdict, isLoading, error } = useQuery<CompanyVerdict>({
    queryKey: ['company-verdict', companyId],
    queryFn: () => analysisService.getCompanyVerdict(companyId),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2">
        <div className="h-4 bg-white/5 rounded w-1/4"></div>
        <div className="h-10 bg-white/[0.02] rounded"></div>
      </div>
    );
  }

  if (error || !verdict) {
    return null;
  }

  const getTargetFitBadge = (fit: string) => {
    if (fit === 'primary') {
      return (
        <span className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
          Strong Fit
        </span>
      );
    }
    if (fit === 'secondary') {
      return (
        <span className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/20">
          Potential Fit
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-white/5 text-gray-500 ring-1 ring-inset ring-white/10">
        Unclear
      </span>
    );
  };

  const getConfidenceBadge = (confidence: string) => {
    if (confidence === 'high') {
      return (
        <span className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-emerald-500/10 text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
          High
        </span>
      );
    }
    if (confidence === 'medium' || confidence === 'moderate') {
      return (
        <span className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-amber-500/10 text-amber-400 ring-1 ring-inset ring-amber-500/20">
          Medium
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider bg-white/5 text-gray-500 ring-1 ring-inset ring-white/10">
        Low
      </span>
    );
  };

  const formatCompanyType = (type: string) => {
    if (type === 'operating_company') return 'Operating Company';
    if (type === 'job_market_intermediary') return 'Job Market Intermediary';
    return 'Unclear';
  };

  const formatAnalysisMode = (mode: string) => {
    if (mode === 'direct_employer_analysis') return 'Direct Employer Analysis';
    if (mode === 'recruiting_marketplace_analysis') return 'Recruiting Marketplace Analysis';
    return 'Unclear Analysis';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 flex-wrap">
        <div>
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Company Type</p>
          <p className="text-sm font-medium text-gray-200">{formatCompanyType(verdict.company_type)}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Target Fit</p>
          {getTargetFitBadge(verdict.target_fit)}
        </div>
        <div>
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Confidence</p>
          {getConfidenceBadge(verdict.company_type_confidence)}
        </div>
      </div>

      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Analysis Mode</p>
        <p className="text-sm text-gray-400">{formatAnalysisMode(verdict.analysis_mode)}</p>
      </div>

      <div className="pt-2 border-t border-orbital-border">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Why</p>
        <p className="text-sm text-gray-400">{verdict.company_type_reason}</p>
      </div>
    </div>
  );
}