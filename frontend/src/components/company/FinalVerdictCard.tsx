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
  best_attack_angle: string | null;
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
        <div className="h-4 bg-gray-200 rounded w-1/3"></div>
        <div className="h-20 bg-gray-100 rounded"></div>
      </div>
    );
  }

  if (error || !verdict?.final_verdict) {
    return null;
  }

  const v = verdict.final_verdict;

  if (v.verdict_type === 'preliminary') {
    const pressureColor = v.hiring_pressure === 'high' ? 'bg-red-100 text-red-800' : v.hiring_pressure === 'moderate' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800';
    const clarityColor = v.pain_clarity === 'high' ? 'bg-green-100 text-green-800' : v.pain_clarity === 'moderate' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800';

    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
            Preliminary Verdict
          </span>
          <span className="text-xs text-gray-500">
            Confidence: {v.confidence}
          </span>
        </div>

        {/* Business Read Section */}
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Business Read</p>
          
          <div className="flex gap-4">
            <div>
              <p className="text-xs text-gray-400 mb-1">Hiring Pressure</p>
              <span className={`inline-flex items-center px-2 py-1 rounded text-sm font-medium ${pressureColor}`}>
                {v.hiring_pressure || 'N/A'}
              </span>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Pain Clarity</p>
              <span className={`inline-flex items-center px-2 py-1 rounded text-sm font-medium ${clarityColor}`}>
                {v.pain_clarity || 'N/A'}
              </span>
            </div>
          </div>

          {v.diagnosis_status && (
            <div>
              <p className="text-xs text-gray-400 mb-1">Diagnosis Status</p>
              <p className="text-sm text-gray-700">
                {v.diagnosis_status === 'broad_hiring_pattern_detected' && 'Broad hiring pattern detected; specific pain not yet isolated.'}
                {v.diagnosis_status === 'insufficient_evidence' && 'Not enough evidence to analyze yet.'}
                {v.diagnosis_status === 'specific_pain_emerging' && 'Specific pain is beginning to emerge.'}
                {v.diagnosis_status === 'specific_pain_identified' && 'Specific pain has been identified.'}
              </p>
            </div>
          )}

          {v.business_read_summary && (
            <div className="pt-2 border-t border-gray-200">
              <p className="text-sm text-gray-700">{v.business_read_summary}</p>
            </div>
          )}
        </div>

        {v.what_we_know && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we know</p>
            <p className="text-sm text-gray-700">{v.what_we_know}</p>
          </div>
        )}

        {v.what_we_do_not_know_yet && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">What we do not know yet</p>
            <p className="text-sm text-gray-600">{v.what_we_do_not_know_yet}</p>
          </div>
        )}

        {v.next_best_step && (
          <div className="bg-amber-50 border border-amber-100 rounded px-4 py-3">
            <p className="text-xs text-amber-600 uppercase tracking-wide mb-1">Next best step</p>
            <p className="text-sm text-gray-700">{v.next_best_step}</p>
          </div>
        )}
      </div>
    );
  }

  const pressureColor = v.hiring_pressure === 'high' ? 'bg-red-100 text-red-800' : v.hiring_pressure === 'moderate' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800';
  const clarityColor = v.pain_clarity === 'high' ? 'bg-green-100 text-green-800' : v.pain_clarity === 'moderate' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
          Final Verdict
        </span>
        <span className="text-xs text-gray-500">
          Confidence: {v.confidence}
        </span>
      </div>

      {/* Business Read Section */}
      {(v.hiring_pressure || v.pain_clarity) && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Business Read</p>
          
          <div className="flex gap-4">
            <div>
              <p className="text-xs text-gray-400 mb-1">Hiring Pressure</p>
              <span className={`inline-flex items-center px-2 py-1 rounded text-sm font-medium ${pressureColor}`}>
                {v.hiring_pressure || 'N/A'}
              </span>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Pain Clarity</p>
              <span className={`inline-flex items-center px-2 py-1 rounded text-sm font-medium ${clarityColor}`}>
                {v.pain_clarity || 'N/A'}
              </span>
            </div>
          </div>

          {v.diagnosis_status && (
            <div>
              <p className="text-xs text-gray-400 mb-1">Diagnosis Status</p>
              <p className="text-sm text-gray-700">
                {v.diagnosis_status === 'specific_pain_identified' && 'Specific pain has been identified.'}
                {v.diagnosis_status === 'specific_pain_emerging' && 'Specific pain is beginning to emerge.'}
              </p>
            </div>
          )}
        </div>
      )}

      <div>
        <p className="text-xs text-red-600 uppercase tracking-wide mb-1">Main Pain</p>
        <p className="text-sm text-gray-800">{v.main_pain}</p>
      </div>

      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Where the pain lives</p>
        <p className="text-sm text-gray-700">{v.where_pain_lives}</p>
      </div>

      <div className="bg-emerald-50 border border-emerald-100 rounded px-4 py-3">
        <p className="text-xs text-emerald-600 uppercase tracking-wide mb-1">What the company likely needs</p>
        <p className="text-sm text-gray-800">{v.what_the_company_needs}</p>
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded px-4 py-3">
        <p className="text-xs text-blue-600 uppercase tracking-wide mb-1">Best attack angle</p>
        <p className="text-sm text-gray-700">{v.best_attack_angle}</p>
      </div>
    </div>
  );
}