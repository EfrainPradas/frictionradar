import { useQuery } from '@tanstack/react-query';
import { analysisService, type CompanyEvaluation } from '../../services/analysis';

interface HiringPattern {
  top_functional_areas: string;
  total_roles_found: number;
  unique_functions_found: number;
}

interface JobRole {
  role_title: string;
  functional_area: string;
  functional_area_confidence: string;
  source_url: string;
}

interface PageEvidence {
  open_positions_count: number;
  visible_categories: string[];
  job_cards_count: number;
  evidence_quality: string;
}

interface HiringIntelligence {
  hiring_pattern: HiringPattern | null;
  job_roles: JobRole[];
  page_evidence: PageEvidence | null;
}

interface Props {
  companyId: string;
  evaluation?: CompanyEvaluation;
}

function hasBroadHiringEvidence(evaluation?: CompanyEvaluation): boolean {
  if (!evaluation) return false;
  const ev = evaluation.evidence;
  return (
    ev.visible_hiring_areas >= 2
    || ev.distinct_signal_types >= 3
    || ev.open_positions_count >= 20
  );
}

export function HiringIntelligenceCard({ companyId, evaluation }: Props) {
  const { data, isLoading } = useQuery<HiringIntelligence>({
    queryKey: ['hiring-intelligence', companyId],
    queryFn: () => analysisService.getHiringIntelligence(companyId),
    enabled: !!companyId,
  });

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-3">
        <div className="h-4 bg-gray-200 rounded w-1/4"></div>
        <div className="h-20 bg-gray-100 rounded"></div>
      </div>
    );
  }

  const pattern = data?.hiring_pattern;
  const roles = data?.job_roles || [];
  const pageEvidence = data?.page_evidence;
  
  // Handle empty data
  if (!pattern && !pageEvidence && roles.length === 0) {
    return (
      <div className="space-y-2">
        {hasBroadHiringEvidence(evaluation) ? (
          <>
            <p className="text-sm text-gray-700">
              We extracted broad hiring-area evidence, but still lack enough repeated role-family detail to isolate the dominant pain.
            </p>
            <p className="text-xs text-gray-500">
              Current evidence points to broad business demand, not yet a concentrated function-specific pain.
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-600">
            We found the careers page, but were not able to extract enough role-level detail yet.
          </p>
        )}
      </div>
    );
  }

  // Page-level evidence display
  if (pageEvidence) {
    const { open_positions_count, visible_categories, evidence_quality } = pageEvidence;
    
    return (
      <div className="space-y-4">
        {/* Visible hiring volume */}
        {open_positions_count > 0 && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Visible hiring volume</p>
            <p className="text-lg font-semibold text-gray-800">
              {open_positions_count.toLocaleString()} open positions
            </p>
          </div>
        )}

        {/* Top visible hiring areas */}
        {visible_categories && visible_categories.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Top visible hiring areas</p>
            <div className="flex flex-wrap gap-2">
              {visible_categories.slice(0, 5).map((area, idx) => (
                <span 
                  key={idx}
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    idx === 0 
                      ? 'bg-red-100 text-red-700' 
                      : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {area.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Sample visible roles */}
        {roles.length > 0 && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Sample visible roles</p>
            <ul className="space-y-1">
              {roles.slice(0, 5).map((r, idx) => (
                <li key={idx} className="text-sm text-gray-700 flex items-center gap-2">
                  <span className="text-gray-400">•</span>
                  <span>{r.role_title}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Evidence quality badge */}
        <div className="pt-2 border-t border-gray-100">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
            evidence_quality === 'moderate'
              ? 'bg-yellow-100 text-yellow-700'
              : 'bg-gray-100 text-gray-600'
          }`}>
            Evidence: {evidence_quality}
          </span>
        </div>
      </div>
    );
  }

  // Fallback to role-based display (for parsed job roles)
  const topAreas = pattern?.top_functional_areas?.split(', ').slice(0, 3) || [];
  const sampleRoles = roles.slice(0, 5).map(r => r.role_title);

  if (roles.length === 0 && !pattern) {
    return (
      <div className="space-y-2">
        {hasBroadHiringEvidence(evaluation) ? (
          <>
            <p className="text-sm text-gray-700">
              We extracted broad hiring-area evidence, but still lack enough repeated role-family detail to isolate the dominant pain.
            </p>
            <p className="text-xs text-gray-500">
              Current evidence points to broad business demand, not yet a concentrated function-specific pain.
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-600">
            We found the careers page, but were not able to extract enough role-level detail yet.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Top Hiring Areas */}
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Top functional areas hiring</p>
        <div className="flex flex-wrap gap-2">
          {topAreas.map((area, idx) => (
            <span 
              key={idx}
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                idx === 0 
                  ? 'bg-red-100 text-red-700' 
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              {area}
            </span>
          ))}
        </div>
      </div>

      {/* Summary stats */}
      <div className="flex gap-4 text-sm">
        <div>
          <span className="text-gray-400">Roles found: </span>
          <span className="font-medium">{pattern?.total_roles_found || roles.length}</span>
        </div>
        <div>
          <span className="text-gray-400">Functions: </span>
          <span className="font-medium">{pattern?.unique_functions_found || 0}</span>
        </div>
      </div>

      {/* Sample roles */}
      {sampleRoles.length > 0 && (
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Sample roles</p>
          <ul className="space-y-1">
            {sampleRoles.map((title, idx) => (
              <li key={idx} className="text-sm text-gray-700 flex items-center gap-2">
                <span className="text-gray-400">•</span>
                <span>{title}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}