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
        <div className="h-4 bg-white/5 rounded w-1/4"></div>
        <div className="h-16 bg-white/[0.02] rounded"></div>
      </div>
    );
  }

  const pattern = data?.hiring_pattern;
  const roles = data?.job_roles || [];
  const pageEvidence = data?.page_evidence;

  const hasAnyEvidence = evaluation && (
    evaluation.evidence.open_positions_count > 0
    || evaluation.evidence.visible_hiring_areas > 0
    || evaluation.evidence.distinct_signal_types > 0
    || evaluation.evidence.parsed_titles > 0
  );

  if (!pattern && !pageEvidence && roles.length === 0) {
    return (
      <div className="space-y-2">
        {hasBroadHiringEvidence(evaluation) ? (
          <>
            <p className="text-sm text-gray-300">
              We extracted broad hiring-area evidence, but still lack enough repeated role-family detail to isolate the dominant pain.
            </p>
            <p className="text-xs text-gray-500">
              Current evidence points to broad business demand, not yet a concentrated function-specific pain.
            </p>
          </>
        ) : hasAnyEvidence ? (
          <p className="text-sm text-gray-500">
            We found the careers page, but were not able to extract enough role-level detail yet.
          </p>
        ) : (
          <p className="text-sm text-gray-500">
            No hiring signals detected for this company yet. We'll update when positions become available.
          </p>
        )}
      </div>
    );
  }

  if (pageEvidence) {
    const { open_positions_count, visible_categories, evidence_quality } = pageEvidence;

    return (
      <div className="space-y-4">
        {open_positions_count > 0 && (
          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-1">Visible hiring volume</p>
            <p className="text-lg font-semibold text-gray-200">
              {open_positions_count.toLocaleString()} open positions
            </p>
          </div>
        )}

        {visible_categories && visible_categories.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">Top visible hiring areas</p>
            <div className="flex flex-wrap gap-2">
              {visible_categories.slice(0, 5).map((area, idx) => (
                <span
                  key={idx}
                  className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                    idx === 0
                      ? 'bg-red-500/10 text-red-400 ring-1 ring-inset ring-red-500/20'
                      : 'bg-white/5 text-gray-400 ring-1 ring-inset ring-white/10'
                  }`}
                >
                  {area.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {roles.length > 0 && (
          <div>
            <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">Sample visible roles</p>
            <ul className="space-y-1">
              {roles.slice(0, 5).map((r, idx) => (
                <li key={idx} className="text-sm text-gray-300 flex items-center gap-2">
                  <span className="text-gray-600">•</span>
                  <span>{r.role_title}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="pt-2 border-t border-orbital-border">
          <span className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1 ring-inset ${
            evidence_quality === 'moderate'
              ? 'bg-amber-500/10 text-amber-400 ring-amber-500/20'
              : 'bg-white/5 text-gray-500 ring-white/10'
          }`}>
            Evidence: {evidence_quality}
          </span>
        </div>
      </div>
    );
  }

  const topAreas = pattern?.top_functional_areas?.split(', ').slice(0, 3) || [];
  const sampleRoles = roles.slice(0, 5).map(r => r.role_title);

  if (roles.length === 0 && !pattern) {
    return (
      <div className="space-y-2">
        {hasBroadHiringEvidence(evaluation) ? (
          <>
            <p className="text-sm text-gray-300">
              We extracted broad hiring-area evidence, but still lack enough repeated role-family detail to isolate the dominant pain.
            </p>
            <p className="text-xs text-gray-500">
              Current evidence points to broad business demand, not yet a concentrated function-specific pain.
            </p>
          </>
        ) : hasAnyEvidence ? (
          <p className="text-sm text-gray-500">
            We found the careers page, but were not able to extract enough role-level detail yet.
          </p>
        ) : (
          <p className="text-sm text-gray-500">
            No hiring signals detected for this company yet. We'll update when positions become available.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Top Hiring Areas */}
      <div>
        <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">Top functional areas hiring</p>
        <div className="flex flex-wrap gap-2">
          {topAreas.map((area, idx) => (
            <span
              key={idx}
              className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                idx === 0
                  ? 'bg-red-500/10 text-red-400 ring-1 ring-inset ring-red-500/20'
                  : 'bg-white/5 text-gray-400 ring-1 ring-inset ring-white/10'
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
          <span className="text-gray-600">Roles found: </span>
          <span className="font-medium text-gray-300">{pattern?.total_roles_found || roles.length}</span>
        </div>
        <div>
          <span className="text-gray-600">Functions: </span>
          <span className="font-medium text-gray-300">{pattern?.unique_functions_found || 0}</span>
        </div>
      </div>

      {/* Sample roles */}
      {sampleRoles.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500 mb-2">Sample roles</p>
          <ul className="space-y-1">
            {sampleRoles.map((title, idx) => (
              <li key={idx} className="text-sm text-gray-300 flex items-center gap-2">
                <span className="text-gray-600">•</span>
                <span>{title}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}