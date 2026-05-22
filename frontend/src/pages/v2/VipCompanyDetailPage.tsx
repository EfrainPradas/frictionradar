import { useParams, useNavigate, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { apiClient } from '../../services/apiClient';
import { getCompanyPainProfile, type CompanyPainProfile } from '../../services/intelligence';
import { signalsService } from '../../services/signals';
import type { CompanySignal as ApiSignal } from '../../types/signal';
import { RADAR_DIMENSIONS } from '../../data/taxonomy';

type SignalKind = 'job' | 'leadership' | 'news' | 'investment' | 'tech';

const SIGNAL_BADGE: Record<SignalKind, { label: string; cls: string }> = {
  job: { label: 'Job', cls: 'text-blue-700 bg-blue-50 border-blue-200' },
  leadership: { label: 'Leadership', cls: 'text-violet-700 bg-violet-50 border-violet-200' },
  news: { label: 'News', cls: 'text-slate-700 bg-slate-50 border-slate-200' },
  investment: { label: 'Investment', cls: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  tech: { label: 'Tech', cls: 'text-amber-700 bg-amber-50 border-amber-200' },
};

function mapSignalKind(signalType: string): SignalKind {
  const t = signalType.toLowerCase();
  if (t.includes('hir') || t.includes('job') || t.includes('role') || t.includes('career') || t.includes('recruit') || t.includes('position')) return 'job';
  if (t.includes('leader') || t.includes('exec') || t.includes('director') || t.includes('vp') || t.includes('chief')) return 'leadership';
  if (t.includes('invest') || t.includes('fund') || t.includes('round') || t.includes('acquisition')) return 'investment';
  if (t.includes('tech') || t.includes('stack') || t.includes('tool') || t.includes('platform') || t.includes('engineer') || t.includes('data_science') || t.includes('ai')) return 'tech';
  return 'news';
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  careers_page: 'Careers Page',
  ats_board: 'ATS Board',
  newsroom: 'Newsroom',
  public_review: 'Public Review',
  funding_database: 'Funding Database',
  linkedin: 'LinkedIn',
  glassdoor: 'Glassdoor',
  crunchbase: 'Crunchbase',
  g2: 'G2 Reviews',
  techcrunch: 'TechCrunch',
  indeed: 'Indeed',
  company_website: 'Company Website',
  sec_filing: 'SEC Filing',
  press_release: 'Press Release',
};

const PAIN_LABELS: Record<string, string> = {
  reporting_fragmentation: 'Reporting Fragmentation',
  process_inefficiency: 'Process Inefficiency',
  tooling_inconsistency: 'Tooling Inconsistency',
  scaling_strain: 'Scaling Strain',
  customer_experience_friction: 'Customer Experience Friction',
};

interface CompanyData {
  id: string;
  name: string;
  inferred_sector: string | null;
  industry: string | null;
  website: string | null;
}

interface HiringData {
  hiring_pattern: { top_functional_areas: string | null; total_roles_found: number } | null;
  job_roles: { role_title: string; functional_area: string | null; source_url: string | null; functional_area_confidence: string | null }[];
}

export function VipCompanyDetailPage() {
  const { companyId } = useParams();
  const navigate = useNavigate();
  const [company, setCompany] = useState<CompanyData | null>(null);
  const [painProfile, setPainProfile] = useState<CompanyPainProfile | null>(null);
  const [signals, setSignals] = useState<ApiSignal[]>([]);
  const [hiring, setHiring] = useState<HiringData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    Promise.all([
      apiClient.get(`/companies/${companyId}`).then(r => r.data).catch(() => null),
      getCompanyPainProfile(companyId).catch(() => null),
      signalsService.list(companyId).catch(() => []),
      apiClient.get(`/companies/${companyId}/hiring-intelligence`).then(r => r.data).catch(() => null),
    ]).then(([comp, pain, sigs, hire]) => {
      setCompany(comp);
      setPainProfile(pain);
      setSignals(sigs || []);
      setHiring(hire);
      setLoading(false);
    });
  }, [companyId]);

  if (loading) {
    return (
      <div className="p-7 max-w-4xl mx-auto">
        <div className="rounded-lg border border-fr-line bg-fr-paper p-8 text-center">
          <div className="text-sm text-fr-ink-mute">Loading company intelligence...</div>
        </div>
      </div>
    );
  }

  if (!company) {
    return (
      <div className="p-7 max-w-4xl mx-auto">
        <div className="rounded-lg border border-fr-line bg-fr-paper p-8 text-center">
          <div className="text-sm text-fr-ink-mute">Company not found.</div>
          <button onClick={() => navigate('/opportunities')} className="mt-3 text-[12px] font-semibold text-fr-gold hover:underline">
            ← Back to Opportunities
          </button>
        </div>
      </div>
    );
  }

  const dominantPain = painProfile?.dominant_pain || 'scaling_strain';
  const painLabel = PAIN_LABELS[dominantPain] || dominantPain;
  const topRoles = (hiring?.job_roles || []).filter(r =>
    r.functional_area_confidence !== 'none:junk' &&
    r.functional_area !== 'junk' &&
    r.functional_area !== 'unknown'
  ).slice(0, 8);

  return (
    <div className="p-7 max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <header className="rounded-lg border border-fr-line bg-fr-paper p-6">
        <div className="flex items-center gap-2 mb-1">
          <button onClick={() => navigate('/opportunities')} className="text-[11px] text-fr-gold hover:underline">
            ← Back to Opportunities
          </button>
        </div>
        <h1 className="text-[26px] font-semibold text-fr-ink leading-tight">{company.name}</h1>
        <div className="text-[12px] text-fr-ink-mute mt-1.5">
          {company.industry || 'Industry not specified'}
          {company.website && (
            <> · <a href={company.website} target="_blank" rel="noreferrer" className="text-fr-gold hover:underline">{company.website.replace(/^https?:\/\//, '')}</a></>
          )}
        </div>
        <p className="text-[13px] text-fr-ink-soft mt-3 max-w-2xl leading-relaxed">
          Primary friction: <span className="font-semibold text-fr-ink">{painLabel}</span>.
          {signals.length > 0 && <> Evidence from {signals.length} observable signals.</>}
        </p>
      </header>

      {/* Open Roles */}
      {topRoles.length > 0 && (
        <section className="rounded-lg border border-fr-line bg-fr-paper">
          <div className="px-5 py-4 border-b border-fr-line">
            <div className="text-[14px] font-semibold text-fr-ink">Open Positions</div>
            <div className="text-[11px] text-fr-ink-mute mt-0.5">
              Active roles where your experience aligns with their organizational pain.
            </div>
          </div>
          <ul className="divide-y divide-fr-line">
            {topRoles.map((role, i) => (
              <li key={i} className="px-5 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[13px] font-medium text-fr-ink leading-snug">
                    {role.source_url ? (
                      <a href={role.source_url} target="_blank" rel="noreferrer" className="hover:underline text-fr-gold">
                        {role.role_title}
                      </a>
                    ) : (
                      role.role_title
                    )}
                  </div>
                  {role.functional_area && (
                    <div className="text-[10px] text-fr-ink-faint mt-0.5 capitalize">
                      {role.functional_area.replace(/_/g, ' ')}
                    </div>
                  )}
                </div>
                {role.source_url && (
                  <a href={role.source_url} target="_blank" rel="noreferrer"
                     className="shrink-0 text-[11px] font-semibold text-fr-paper bg-fr-gold rounded-md px-3 py-1.5 hover:bg-fr-gold/90 transition-colors">
                    Apply →
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Pain Profile */}
      {painProfile && (
        <section className="rounded-lg border border-fr-line bg-fr-paper p-5">
          <div className="text-[14px] font-semibold text-fr-ink mb-3">Organizational Pain Profile</div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Dominant Pain</div>
              <div className="text-[13px] font-medium text-fr-ink">{painLabel}</div>
            </div>
            {painProfile.confidence_band && (
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Confidence</div>
                <div className="text-[13px] capitalize text-fr-ink">{painProfile.confidence_band}</div>
              </div>
            )}
            {painProfile.positioning_angle && (
              <div className="col-span-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-fr-ink-faint mb-1">Positioning Angle</div>
                <div className="text-[13px] text-fr-ink-soft leading-relaxed">{painProfile.positioning_angle}</div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Key Signals */}
      {signals.length > 0 && (
        <section className="rounded-lg border border-fr-line bg-fr-paper">
          <div className="px-5 py-4 border-b border-fr-line">
            <div className="text-[14px] font-semibold text-fr-ink">Key Signals</div>
            <div className="text-[11px] text-fr-ink-mute mt-0.5">Observable inputs feeding the friction score.</div>
          </div>
          <ul className="divide-y divide-fr-line">
            {signals.slice(0, 10).map((s) => {
              const kind = mapSignalKind(s.signal_type);
              const badge = SIGNAL_BADGE[kind];
              const daysAgo = s.captured_at
                ? Math.max(0, Math.round((Date.now() - new Date(s.captured_at).getTime()) / 86400000))
                : 0;
              return (
                <li key={s.id} className="px-5 py-3 flex items-start gap-3">
                  <span className={`shrink-0 inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.cls}`}>
                    {badge.label}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] text-fr-ink-soft leading-snug">{s.signal_text}</div>
                    <div className="text-[10px] font-mono tracking-wide text-fr-ink-faint mt-1">
                      {s.signal_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      {s.confidence ? ` · ${Math.round(s.confidence * 100)}%` : ''} · {daysAgo}d ago
                    </div>
                    {s.source_url && (
                      <a href={s.source_url} target="_blank" rel="noreferrer" className="text-[11px] text-fr-gold hover:underline mt-1 inline-block">
                        Open source →
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}