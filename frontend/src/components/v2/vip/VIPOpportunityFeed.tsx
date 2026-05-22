import { useState } from 'react';

interface VipOpenRole {
  title: string;
  url?: string | null;
  functional_area?: string | null;
  location?: string | null;
}

interface VipOpportunity {
  company_id: string;
  company_name?: string | null;
  alignment_score: number;
  opportunity_type?: string | null;
  company_pain_summary?: string | null;
  strategic_positioning?: string | null;
  why_you_fit?: string | null;
  why_they_value_you?: string | null;
  resume_emphasis?: string[];
  networking_positioning?: string | null;
  interview_positioning?: string | null;
  open_roles?: VipOpenRole[];
}

interface Props {
  opportunities: VipOpportunity[];
  onCompanyClick?: (companyId: string) => void;
}

const TIER_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  stable_fit: { bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'Strong Fit' },
  accelerated_positioning: { bg: 'bg-amber-50', text: 'text-amber-700', label: 'Accelerated' },
  early_positioning: { bg: 'bg-slate-50', text: 'text-slate-500', label: 'Emerging' },
};

export function VIPOpportunityFeed({ opportunities, onCompanyClick }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!opportunities.length) {
    return (
      <div className="rounded-lg border border-fr-line bg-fr-paper p-8 text-center">
        <div className="text-sm text-fr-ink-mute mb-1">No VIP opportunities yet</div>
        <div className="text-xs text-fr-ink-faint">
          Complete your profile to discover where your experience is most strategically valuable.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {opportunities.map((opp) => {
        const tier = TIER_STYLES[opp.opportunity_type || ''] || TIER_STYLES.early_positioning;
        const scorePercent = Math.round(opp.alignment_score * 100);
        const isExpanded = expandedId === opp.company_id;

        return (
          <div
            key={opp.company_id}
            className="rounded-lg border border-fr-line bg-fr-paper overflow-hidden hover:shadow-sm transition-shadow"
          >
            {/* Company header — clickable to expand */}
            <button
              type="button"
              onClick={() => setExpandedId(isExpanded ? null : opp.company_id)}
              className="w-full text-left px-4 py-3 flex items-center justify-between border-b border-fr-line hover:bg-fr-overlay/40 transition-colors"
            >
              <div className="min-w-0">
                <div className="text-[13.5px] font-semibold text-fr-ink leading-tight">
                  {opp.company_name || opp.company_id}
                </div>
                {opp.company_pain_summary && !isExpanded && (
                  <p className="text-[11px] text-fr-ink-mute mt-0.5 truncate">{opp.company_pain_summary}</p>
                )}
              </div>
              <div className="flex items-center gap-2.5 shrink-0 ml-3">
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${tier.bg} ${tier.text}`}>
                  {tier.label}
                </span>
                <div className="flex items-center gap-1.5">
                  <div className="w-14 h-1.5 rounded-full bg-fr-line overflow-hidden">
                    <div
                      className={`h-full rounded-full ${scorePercent >= 65 ? 'bg-emerald-400' : scorePercent >= 35 ? 'bg-amber-400' : 'bg-slate-300'}`}
                      style={{ width: `${scorePercent}%` }}
                    />
                  </div>
                  <span className="text-[11px] font-mono text-fr-ink-soft">{scorePercent}%</span>
                </div>
                <span className={`text-[10px] text-fr-ink-faint transition-transform ${isExpanded ? 'rotate-180' : ''}`}>▾</span>
              </div>
            </button>

            {/* Expanded detail */}
            {isExpanded && (
              <div className="divide-y divide-fr-line">
                {/* Why you fit */}
                {opp.why_you_fit && (
                  <div className="px-4 py-3">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Why You Fit</div>
                    <p className="text-xs text-fr-ink-soft leading-relaxed">{opp.why_you_fit}</p>
                  </div>
                )}

                {/* Why they value you */}
                {opp.why_they_value_you && (
                  <div className="px-4 py-3 bg-fr-gold-tint/30">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-fr-gold mb-1">Why They May Value You</div>
                    <p className="text-xs text-fr-ink leading-relaxed">{opp.why_they_value_you}</p>
                  </div>
                )}

                {/* Strategic positioning */}
                {opp.strategic_positioning && (
                  <div className="px-4 py-3">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Strategic Positioning</div>
                    <p className="text-xs text-fr-ink-soft leading-relaxed">{opp.strategic_positioning}</p>
                  </div>
                )}

                {/* Resume emphasis */}
                {opp.resume_emphasis && opp.resume_emphasis.length > 0 && (
                  <div className="px-4 py-3">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1.5">Resume Emphasis</div>
                    <div className="flex flex-wrap gap-1.5">
                      {opp.resume_emphasis.map((item, i) => (
                        <span key={i} className="inline-flex items-center px-2.5 py-1 rounded-md bg-fr-gold-tint text-fr-gold text-[11px] font-medium">
                          {item.length > 50 ? item.slice(0, 50) + '...' : item}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Open Roles */}
                {opp.open_roles && opp.open_roles.length > 0 && (
                  <div className="px-4 py-3">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1.5">Open Roles</div>
                    <ul className="space-y-1.5">
                      {opp.open_roles.slice(0, 5).map((role, i) => (
                        <li key={i} className="flex items-start gap-2 text-[12px]">
                          <span className="shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full bg-fr-gold" />
                          <div className="min-w-0">
                            <div className="text-fr-ink-soft leading-snug">
                              {role.url ? (
                                <a href={role.url} target="_blank" rel="noreferrer" className="text-fr-gold hover:underline">
                                  {role.title}
                                </a>
                              ) : (
                                <span>{role.title}</span>
                              )}
                            </div>
                            {(role.functional_area || role.location) && (
                              <div className="text-[10px] text-fr-ink-faint mt-0.5">
                                {[role.functional_area, role.location].filter(Boolean).join(' · ')}
                              </div>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Networking & Interview guidance */}
                <div className="px-4 py-3 grid grid-cols-2 gap-4">
                  {opp.networking_positioning && (
                    <div>
                      <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Networking Angle</div>
                      <p className="text-xs text-fr-ink-soft leading-relaxed">{opp.networking_positioning}</p>
                    </div>
                  )}
                  {opp.interview_positioning && (
                    <div>
                      <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Interview Positioning</div>
                      <p className="text-xs text-fr-ink-soft leading-relaxed">{opp.interview_positioning}</p>
                    </div>
                  )}
                </div>

                {/* CTA — View full analysis */}
                <div className="px-4 py-3 bg-fr-paper-2">
                  <button
                    type="button"
                    onClick={() => onCompanyClick?.(opp.company_id)}
                    className="w-full rounded-md bg-fr-ink text-fr-paper text-[12px] font-semibold py-2.5 hover:bg-fr-ink-soft transition-colors"
                  >
                    View Company Analysis →
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}