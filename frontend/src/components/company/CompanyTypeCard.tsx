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
    best_attack_angle: string;
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
      <div className="animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-1/4 mb-2"></div>
        <div className="h-20 bg-gray-100 rounded"></div>
      </div>
    );
  }

  if (error || !verdict) {
    return null;
  }

  const getTargetFitBadge = (fit: string) => {
    if (fit === 'primary') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
          Primary Target
        </span>
      );
    }
    if (fit === 'secondary') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
          Secondary Target
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
        Unclear
      </span>
    );
  };

  const getConfidenceBadge = (confidence: string) => {
    if (confidence === 'high') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
          High
        </span>
      );
    }
    if (confidence === 'medium') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
          Medium
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
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
      <div className="flex items-center gap-3 flex-wrap">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Company Type</p>
          <p className="text-sm font-medium text-gray-900">{formatCompanyType(verdict.company_type)}</p>
        </div>
        <div className="ml-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Target Fit</p>
          {getTargetFitBadge(verdict.target_fit)}
        </div>
        <div className="ml-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Confidence</p>
          {getConfidenceBadge(verdict.company_type_confidence)}
        </div>
      </div>
      
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Analysis Mode</p>
        <p className="text-sm text-gray-600">{formatAnalysisMode(verdict.analysis_mode)}</p>
      </div>

      <div className="pt-2 border-t border-gray-100">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Why</p>
        <p className="text-sm text-gray-600">{verdict.company_type_reason}</p>
      </div>
    </div>
  );
}