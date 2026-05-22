import { SECTORS, RADAR_DIMENSIONS } from './taxonomy';
import { HEATMAP_CELLS } from './mockHeatmap';

export type RadarDim = (typeof RADAR_DIMENSIONS)[number]['slug'];

export interface SectorRadar {
  reporting: number;
  process: number;
  tooling: number;
  scaling: number;
  cx: number;
}

export interface SectorCompany {
  id: string;
  name: string;
  primaryPain: string;
  primaryPainDim: RadarDim;
  pressure: number;
  trend: 'rising' | 'moderate' | 'stable' | 'easing';
}

export interface SectorAggregate {
  slug: string;
  label: string;
  pressure: number;
  velocityPct: number;
  companiesTracked: number;
  radar: SectorRadar;
  dominantDim: RadarDim;
  companies: SectorCompany[];
}

const DIM_LABELS: Record<RadarDim, string> = {
  reporting: 'Reporting Fragmentation',
  process: 'Process Inefficiency',
  tooling: 'Tool Sprawl',
  scaling: 'Scaling Pressure',
  cx: 'Customer Experience Strain',
};

const COMPANY_POOL: Record<string, string[]> = {
  'software-saas': ['Helix Labs', 'Northwind Systems', 'Glasshouse', 'Stratus Cloud', 'Pact Health'],
  'ai-ml': ['Tessera AI', 'Aspect AI', 'Linde Analytics', 'Mosaic Reasoning', 'Driftline AI'],
  'fintech': ['Arclight Capital', 'Mosaic Bank', 'Beacon Trust', 'Mirador Finance', 'Saltspring Pay'],
  'healthcare-biotech': ['Vector Health', 'Pact Health', 'Hummingbird Bio', 'Coastal Genomics', 'Lumen Care'],
  'retail': ['Stratus Retail', 'Mercato', 'Citrine Markets', 'Wayfinder Retail', 'Open Field'],
  'logistics': ['Quanta Logistics', 'Citrine Logistics', 'Riverstone Freight', 'Kinetic Foundry', 'Boreal Mfg'],
  'cybersecurity': ['PrismSec', 'Carbon Nine', 'Forge & Co', 'Saltspring Security', 'Beacon Defense'],
  'media': ['Vox Media', 'BuzzFeed', 'Condé Nast', 'The Atlantic', 'Vice Media'],
  'manufacturing': ['Boreal Mfg', 'Forge & Co', 'Coastal Robotics', 'Carbon Nine', 'Loomwave'],
  'finance': ['Mosaic Bank', 'Arclight Capital', 'Beacon Trust', 'Mirador Finance', 'Riverstone'],
};

const PAIN_COPY: Record<RadarDim, string[]> = {
  reporting: ['Reporting Fragmentation', 'Dashboard Duplication', 'KPI Ownership Gap'],
  process: ['Process Inefficiency', 'Cross-team Handoffs', 'Manual Reconciliation'],
  tooling: ['Tool Sprawl', 'Legacy CRM Drag', 'Data Stack Migration'],
  scaling: ['Scaling Pressure', 'Org Doubling Strain', 'Hiring Spike Backlog'],
  cx: ['Customer Experience Strain', 'NPS Collapse', 'Support Backlog'],
};

const TREND_FROM_VEL = (v: number): SectorCompany['trend'] => {
  if (v > 0.4) return 'rising';
  if (v > 0.1) return 'moderate';
  if (v < -0.1) return 'easing';
  return 'stable';
};

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

function buildSector(slug: string, label: string): SectorAggregate {
  const cells = HEATMAP_CELLS.filter((c) => c.sector === slug);
  const avg = (k: 'intensity' | 'velocity' | 'opportunity') =>
    cells.reduce((s, c) => s + c[k], 0) / Math.max(cells.length, 1);

  const pressure = Math.round(avg('intensity'));
  const velocityPct = Math.round(avg('velocity') * 100);

  const rnd = mulberry32(hash(slug));
  const radar: SectorRadar = {
    reporting: Math.round(40 + rnd() * 50),
    process: Math.round(40 + rnd() * 50),
    tooling: Math.round(40 + rnd() * 50),
    scaling: Math.round(40 + rnd() * 50),
    cx: Math.round(40 + rnd() * 50),
  };
  const entries = Object.entries(radar) as [RadarDim, number][];
  entries.sort((a, b) => b[1] - a[1]);
  const dominantDim = entries[0][0];
  radar[dominantDim] = Math.max(radar[dominantDim], pressure + 4);

  const names = COMPANY_POOL[slug] ?? ['Acme Co', 'Northwind', 'Globex', 'Initech', 'Umbrella'];
  const companies: SectorCompany[] = names.map((name, i) => {
    const localRnd = mulberry32(hash(`${slug}::${name}`));
    const painDim = entries[i % entries.length][0];
    const painList = PAIN_COPY[painDim];
    const pain = painList[Math.floor(localRnd() * painList.length)];
    const cellVel = cells[i % Math.max(cells.length, 1)]?.velocity ?? 0;
    const pres = Math.round(pressure + (localRnd() - 0.5) * 22);
    return {
      id: `${slug}-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      name,
      primaryPain: pain,
      primaryPainDim: painDim,
      pressure: Math.max(20, Math.min(99, pres)),
      trend: TREND_FROM_VEL(cellVel + (localRnd() - 0.5) * 0.4),
    };
  });

  return {
    slug,
    label,
    pressure,
    velocityPct,
    companiesTracked: 12 + Math.floor(rnd() * 18),
    radar,
    dominantDim,
    companies,
  };
}

export const SECTOR_AGGREGATES: SectorAggregate[] = SECTORS.map((s) => buildSector(s.slug, s.label));

export function getSectorAggregate(slug: string): SectorAggregate | undefined {
  return SECTOR_AGGREGATES.find((s) => s.slug === slug);
}

export function dominantDimLabel(dim: RadarDim): string {
  return DIM_LABELS[dim];
}

export const SECTOR_TAGLINE: Record<string, string> = {
  'software-saas': 'PLG saturation, retention pressure, AI repositioning.',
  'ai-ml': 'Talent war, inference cost spikes, market positioning gap.',
  'fintech': 'Compliance load, infra modernization, fraud ops scaling.',
  'healthcare-biotech': 'Compliance, staffing pressure, operational modernization.',
  'retail': 'Customer experience, logistics, margin optimization.',
  'logistics': 'Last-mile chaos, fleet tech, integration debt.',
  'cybersecurity': 'Tool sprawl, alert fatigue, board-level reporting gap.',
  'media': 'AI transformation, reporting fragmentation, monetization pressure.',
  'manufacturing': 'Supply-chain, OEE visibility, workforce modernization.',
  'finance': 'Risk automation, reporting, data governance.',
};

export const DIMENSION_INTERPRETATION: Record<
  RadarDim,
  { title: string; means: string; angle: string }
> = {
  reporting: {
    title: 'Reporting Fragmentation',
    means:
      'Companies may be struggling with fragmented KPI ownership, dashboard duplication, and unclear decision visibility.',
    angle: 'Operational visibility, analytics governance, and reporting modernization.',
  },
  process: {
    title: 'Process Inefficiency',
    means:
      'Cross-team handoffs are leaking time. Hidden swivel-chair work is showing up in job posts and leadership churn.',
    angle: 'Process diagnostics, RACI redesign, and selective automation of high-friction handoffs.',
  },
  tooling: {
    title: 'Tool Sprawl',
    means:
      'Multiple overlapping tools are creating integration debt. Data is duplicated and trust in metrics is dropping.',
    angle: 'Stack consolidation, integration layer, and platform engineering enablement.',
  },
  scaling: {
    title: 'Scaling Pressure',
    means:
      'Growth has outpaced internal structure. Hiring spikes, new offices and leadership gaps are showing strain.',
    angle: 'Org design, scaling playbooks, and ops/RevOps enablement under growth.',
  },
  cx: {
    title: 'Customer Experience Strain',
    means:
      'Customer signals (NPS, complaints, leadership hires in CX) point to deteriorating post-sale experience.',
    angle: 'CX diagnostics, support tooling rationalization, and onboarding/lifecycle redesign.',
  },
};
