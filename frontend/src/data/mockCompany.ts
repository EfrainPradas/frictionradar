import type { RadarDim, SectorRadar } from './mockSector';
import { SECTOR_AGGREGATES } from './mockSector';

export interface CompanySignal {
  kind: 'job' | 'leadership' | 'news' | 'investment' | 'tech';
  text: string;
  weight: number;
  daysAgo: number;
}

export interface CompanyEvidence {
  source: string;
  url?: string;
  observedAt: string;
  excerpt: string;
}

export interface CompanyDetail {
  id: string;
  name: string;
  sectorSlug: string;
  sectorLabel: string;
  pressure: number;
  velocityPct: number;
  primaryPainDim: RadarDim;
  primaryPainLabel: string;
  hqLine: string;
  sizeBand: string;
  radar: SectorRadar;
  signals: CompanySignal[];
  evidence: CompanyEvidence[];
  positioningAngle: {
    title: string;
    summary: string;
    bullets: string[];
  };
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

const SIGNAL_TEMPLATES: Record<RadarDim, string[]> = {
  reporting: [
    'Open req: Senior Analytics Engineer (3rd posting in 30d)',
    'Hiring Head of Data — first such role at the company',
    'Recent job posts mention "fragmented dashboards" and "manual KPI rollups"',
    'Two BI Manager roles posted last week',
  ],
  process: [
    'Open req: Director of Operations — replacement, 7d ago',
    '3 RevOps roles posted in 30d',
    'Job description cites "scaling chaos" and "ambiguous handoffs"',
    'Acquisition closed last quarter, integration in flight',
  ],
  tooling: [
    'Open req: Platform Engineer x2',
    'Migrating off legacy CRM (job posts mention transition)',
    'RFP open for new data warehouse',
    'Hiring DevTools Lead — first such role',
  ],
  scaling: [
    'Headcount grew 38% in the last 12 months (signals from LinkedIn)',
    'Series C announced 47d ago — $90M raise',
    'Hiring spike: 14 open requisitions in 30d',
    'New LATAM office announced',
  ],
  cx: [
    'NPS dropped 11 points last quarter (G2 + public reviews)',
    'Hiring VP Customer Experience (new role)',
    '4 CX leadership roles posted in 30d',
    'Public complaints up 22% MoM',
  ],
};

const POSITIONING_TEMPLATES: Record<RadarDim, { title: string; summary: string; bullets: string[] }> = {
  reporting: {
    title: 'Reporting Modernization',
    summary:
      'Lead with operational visibility and KPI ownership. Reporting modernization is the entry, BI governance is the wedge.',
    bullets: [
      'Open with KPI ownership audit framed as a 2-week sprint.',
      'Anchor ROI on "decisions accelerated" not "dashboards built".',
      'Cite their recent Head of Data hire as evidence of leadership pull.',
    ],
  },
  process: {
    title: 'Process Diagnostics',
    summary:
      'Lead with cross-team handoff diagnostics. Their hiring pattern suggests Ops leadership is being onboarded — perfect entry.',
    bullets: [
      'Open with a RACI / handoff diagnostic targeting top 3 friction points.',
      'Frame as "scaling enablement" — not "process cleanup".',
      'Reference the recent Director of Ops role as alignment signal.',
    ],
  },
  tooling: {
    title: 'Stack Consolidation',
    summary:
      'Lead with stack rationalization and integration layer. Their tooling migration creates a clear entry window.',
    bullets: [
      'Open with a stack audit + integration architecture review.',
      'Position as "platform enablement" for the new Platform Engineers.',
      'Avoid pitching tools — they are mid-migration. Pitch the layer above.',
    ],
  },
  scaling: {
    title: 'Scaling Playbook',
    summary:
      'Lead with growth-stage org design and RevOps. Recent funding and hiring spike open a 60-90 day window.',
    bullets: [
      'Open with an org-design sprint focused on RevOps and Ops.',
      'Time the outreach to the close of their Series C (~47d ago).',
      'Frame as "scaling playbook", referencing the LATAM expansion.',
    ],
  },
  cx: {
    title: 'CX Diagnostics',
    summary:
      'Lead with customer experience diagnostics. Their NPS drop + leadership hires create an urgent narrative.',
    bullets: [
      'Open with a CX diagnostic anchored on NPS recovery.',
      'Position as "post-sale operating system" — not "support tooling".',
      'Reference the new VP CX role as natural sponsor.',
    ],
  },
};

const EVIDENCE_SOURCES = [
  { source: 'LinkedIn Job Post', urlBase: 'linkedin.com/jobs' },
  { source: 'Company Press Release', urlBase: 'company.com/press' },
  { source: 'Crunchbase Funding', urlBase: 'crunchbase.com' },
  { source: 'G2 Review', urlBase: 'g2.com' },
  { source: 'TechCrunch', urlBase: 'techcrunch.com' },
  { source: 'Glassdoor', urlBase: 'glassdoor.com' },
];

function buildDetail(
  sectorSlug: string,
  sectorLabel: string,
  companyId: string,
  companyName: string,
  primaryPainDim: RadarDim,
  pressure: number,
  velocityPct: number,
): CompanyDetail {
  const rnd = mulberry32(hash(`${sectorSlug}::${companyId}`));

  const radar: SectorRadar = {
    reporting: Math.round(40 + rnd() * 50),
    process: Math.round(40 + rnd() * 50),
    tooling: Math.round(40 + rnd() * 50),
    scaling: Math.round(40 + rnd() * 50),
    cx: Math.round(40 + rnd() * 50),
  };
  radar[primaryPainDim] = Math.max(radar[primaryPainDim], pressure + 5);

  const signalTexts = SIGNAL_TEMPLATES[primaryPainDim];
  const signals: CompanySignal[] = signalTexts.map((text, i) => {
    const kinds: CompanySignal['kind'][] = ['job', 'leadership', 'news', 'investment'];
    return {
      kind: kinds[i % kinds.length],
      text,
      weight: Math.round(60 + rnd() * 35),
      daysAgo: Math.round(2 + rnd() * 28),
    };
  });

  const evidence: CompanyEvidence[] = signals.slice(0, 4).map((s, i) => {
    const src = EVIDENCE_SOURCES[(hash(companyId) + i) % EVIDENCE_SOURCES.length];
    const obs = new Date(Date.now() - s.daysAgo * 24 * 60 * 60 * 1000);
    return {
      source: src.source,
      url: `https://${src.urlBase}/${companyId}-${i}`,
      observedAt: obs.toISOString().slice(0, 10),
      excerpt: s.text,
    };
  });

  const bands = ['51-200', '201-500', '501-1000', '1001-5000'];
  const hqs = ['New York · USA', 'San Francisco · USA', 'Austin · USA', 'London · UK', 'Mexico City · MX'];

  return {
    id: companyId,
    name: companyName,
    sectorSlug,
    sectorLabel,
    pressure,
    velocityPct,
    primaryPainDim,
    primaryPainLabel: POSITIONING_TEMPLATES[primaryPainDim].title,
    hqLine: hqs[hash(companyId) % hqs.length],
    sizeBand: bands[hash(companyId) % bands.length] + ' employees',
    radar,
    signals,
    evidence,
    positioningAngle: POSITIONING_TEMPLATES[primaryPainDim],
  };
}

const CACHE = new Map<string, CompanyDetail>();

export function getCompanyDetail(sectorSlug: string, companyId: string): CompanyDetail | undefined {
  const key = `${sectorSlug}::${companyId}`;
  if (CACHE.has(key)) return CACHE.get(key);

  const sector = SECTOR_AGGREGATES.find((s) => s.slug === sectorSlug);
  if (!sector) return undefined;
  const c = sector.companies.find((c) => c.id === companyId);
  if (!c) return undefined;

  const velocityPct = sector.velocityPct + Math.round((hash(companyId) % 40) - 20);
  const detail = buildDetail(sectorSlug, sector.label, companyId, c.name, c.primaryPainDim, c.pressure, velocityPct);
  CACHE.set(key, detail);
  return detail;
}
