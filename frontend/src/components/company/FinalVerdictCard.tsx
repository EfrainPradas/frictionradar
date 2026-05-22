import { useQuery } from '@tanstack/react-query';
import { analysisService } from '../../services/analysis';

interface FinalVerdict {
  verdict_type: string;
  evidence_quality: string;
  confidence: string;
  hiring_pressure: string | null;
  pain_clarity: string | null;
  diagnosis_status: string | null;
  business_read_summary: string | null;
  main_pain: string | null;
  where_pain_lives: string | null;
  what_the_company_needs: string | null;
  recommended_positioning: string | null;
  what_we_know: string | null;
  what_we_do_not_know_yet: string | null;
  next_best_step: string | null;
}

interface Props {
  companyId: string;
}

export function FinalVerdictCard({ companyId }: Props) {
  const { data: verdict, isLoading, error } = useQuery<{
    company_type: string;
    final_verdict: FinalVerdict;
  }>({
    queryKey: ['company-verdict', companyId],
    queryFn: () => analysisService.getCompanyVerdict(companyId),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-3">
        <div className="h-4 bg-white/5 rounded w-1/3"></div>
        <div className="h-16 bg-white/[0.02] rounded"></div>
      </div>
    );
  }

  if (error || !verdict?.final_verdict) {
    return null;
  }

  const v = verdict.final_verdict;

  const badgeBase = 'inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset';

  if (v.verdict_type === 'preliminary') {
    const pressureStyles: Record<string, string> = {
      high: 'bg-red-500/10 text-red-400 ring-red-500/20',
      moderate: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
      low: 'bg-white/5 text-gray-500 ring-white/10',
    };
    const clarityStyles: Record<string, string> = {
      high: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
      moderate: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
      low: 'bg-white/5 text-gray-500 ring-white/10',
    };

    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`${badgeBase} bg-amber-500/10 text-amber-400 ring-amber-500/20`}>
            Preliminary Verdict
          </span>
          <span className="text-[10px] text-gray-600 uppercase tracking-wider">
            Confidence: {v.confidence}
          </span>
        </div>

        {/* Business Read Section */}
        <div className="bg-[#080b0e] border border-orbital-border rounded-lg p-4 space-y-3">
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500">Business Read</p>

          <div className="flex gap-4">
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Hiring Pressure</p>
              <span className={`${badgeBase} ${pressureStyles[v.hiring_pressure ?? 'low'] ?? pressureStyles.low}`}>
                {v.hiring_pressure || 'N/A'}
              </span>
            </div>
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Pain Clarity</p>
              <span className={`${badgeBase} ${clarityStyles[v.pain_clarity ?? 'low'] ?? clarityStyles.low}`}>
                {v.pain_clarity || 'N/A'}
              </span>
            </div>
          </div>

          {v.diagnosis_status && (
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Diagnosis Status</p>
              <p className="text-sm text-gray-300">
                {v.diagnosis_status === 'broad_hiring_pattern_detected' && 'Broad hiring pattern detected; specific pain not yet isolated.'}
                {v.diagnosis_status === 'insufficient_evidence' && 'Not enough evidence to analyze yet.'}
                {v.diagnosis_status === 'specific_pain_emerging' && 'Specific pain is beginning to emerge.'}
                {v.diagnosis_status === 'specific_pain_identified' && 'Specific pain has been identified.'}
              </p>
            </div>
          )}

          {v.business_read_summary && (
            <div className="pt-2 border-t border-orbital-border">
              <p className="text-sm text-gray-300">{v.business_read_summary}</p>
            </div>
          )}
        </div>

        {v.what_we_know && (
          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">What we know</p>
            <p className="text-sm text-gray-300">{v.what_we_know}</p>
          </div>
        )}

        {v.what_we_do_not_know_yet && (
          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">What we do not know yet</p>
            <p className="text-sm text-gray-400">{v.what_we_do_not_know_yet}</p>
          </div>
        )}

        {v.next_best_step && (
          <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg px-4 py-3">
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-amber-400 mb-1">Next best step</p>
            <p className="text-sm text-gray-300">{v.next_best_step}</p>
          </div>
        )}
      </div>
    );
  }

  const pressureStyles: Record<string, string> = {
    high: 'bg-red-500/10 text-red-400 ring-red-500/20',
    moderate: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
    low: 'bg-white/5 text-gray-500 ring-white/10',
  };
  const clarityStyles: Record<string, string> = {
    high: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20',
    moderate: 'bg-amber-500/10 text-amber-400 ring-amber-500/20',
    low: 'bg-white/5 text-gray-500 ring-white/10',
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`${badgeBase} bg-emerald-500/10 text-emerald-400 ring-emerald-500/20`}>
          Final Verdict
        </span>
        <span className="text-[10px] text-gray-600 uppercase tracking-wider">
          Confidence: {v.confidence}
        </span>
      </div>

      {/* Business Read Section */}
      {(v.hiring_pressure || v.pain_clarity) && (
        <div className="bg-[#080b0e] border border-orbital-border rounded-lg p-4 space-y-3">
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500">Business Read</p>

          <div className="flex gap-4">
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Hiring Pressure</p>
              <span className={`${badgeBase} ${pressureStyles[v.hiring_pressure ?? 'low'] ?? pressureStyles.low}`}>
                {v.hiring_pressure || 'N/A'}
              </span>
            </div>
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Pain Clarity</p>
              <span className={`${badgeBase} ${clarityStyles[v.pain_clarity ?? 'low'] ?? clarityStyles.low}`}>
                {v.pain_clarity || 'N/A'}
              </span>
            </div>
          </div>

          {v.diagnosis_status && (
            <div>
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Diagnosis Status</p>
              <p className="text-sm text-gray-300">
                {v.diagnosis_status === 'specific_pain_identified' && 'Specific pain has been identified.'}
                {v.diagnosis_status === 'specific_pain_emerging' && 'Specific pain is beginning to emerge.'}
              </p>
            </div>
          )}
        </div>
      )}

      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-red-400 mb-1">Main Pain</p>
        <p className="text-sm text-gray-200">{v.main_pain}</p>
      </div>

      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Where the pain lives</p>
        <p className="text-sm text-gray-300">{v.where_pain_lives}</p>
      </div>

      <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg px-4 py-3">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-emerald-400 mb-1">What the company likely needs</p>
        <p className="text-sm text-gray-200">{v.what_the_company_needs}</p>
      </div>

      <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg px-4 py-3">
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-blue-400 mb-1">Recommended positioning</p>
        <p className="text-sm text-gray-300">{v.recommended_positioning}</p>
      </div>
    </div>
  );
}