import { SECTORS, FUNCTIONS, RADAR_DIMENSIONS } from './taxonomy';

export type RadarDimensionSlug = (typeof RADAR_DIMENSIONS)[number]['slug'];

export interface HeatmapCell {
  sector: string;
  function: string;
  intensity: number;
  velocity: number;
  opportunity: number;
  companyCount: number;
  dominantDimension: RadarDimensionSlug;
  topCompanies: { name: string; intensity: number }[];
  notableSignals: string[];
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

const SECTOR_BIAS: Record<string, number> = {
  'software-saas': 0.18,
  'ai-ml': 0.32,
  'fintech': 0.22,
  'healthcare-biotech': 0.12,
  'retail': 0.08,
  'logistics': 0.14,
  'cybersecurity': 0.26,
  'media': -0.04,
  'manufacturing': -0.02,
  'finance': 0.1,
};

const FUNCTION_BIAS: Record<string, number> = {
  'engineering': 0.22,
  'product': 0.16,
  'analytics': 0.2,
  'it': 0.1,
  'sales': 0.04,
  'marketing': -0.02,
  'support': 0.06,
  'operations': 0.18,
  'supply-chain': 0.12,
  'finance': 0.05,
  'people': 0.0,
  'recruiting': -0.04,
  'legal': -0.08,
};

const DIMENSIONS: RadarDimensionSlug[] = ['reporting', 'process', 'tooling', 'scaling', 'cx'];

const SIGNAL_LIBRARY: Record<RadarDimensionSlug, string[]> = {
  reporting: [
    'Hiring 3 BI analysts after Series B',
    'Job posts mention "manual Excel reporting"',
    'New Head of Data role published 9d ago',
    'Open req: Analytics Engineer (urgent flag)',
  ],
  process: [
    'Hiring Ops Manager + 2 Process leads',
    'Acquired competitor — integration in progress',
    'Job posts cite "scaling chaos"',
    'New COO joined 6 weeks ago',
  ],
  tooling: [
    'Migrating off legacy Salesforce instance',
    'RFP open for new data warehouse',
    'Job posts list 9 disparate SaaS tools',
    'Hiring 2 Platform Engineers',
  ],
  scaling: [
    'Hiring spike: 12 reqs in last 30d',
    'New office announced (LATAM)',
    'Series C closed 47d ago',
    'Org doubled headcount in 18 months',
  ],
  cx: [
    'NPS dropped 11 pts last quarter',
    'Hiring 4 CX leaders (Support, Success, Onboarding)',
    'Public complaints up 22% MoM',
    'New VP Customer joined recently',
  ],
};

const COMPANY_POOL = [
  'Helix Labs', 'Northwind Systems', 'Mercato', 'Vector Health', 'Arclight Capital',
  'Boreal Mfg', 'Quanta Logistics', 'PrismSec', 'Loomwave Media', 'Tessera AI',
  'Glasshouse', 'Driftline', 'Stratus Retail', 'Forge & Co', 'Mosaic Bank',
  'Carbon Nine', 'Coastal Robotics', 'Hummingbird', 'Lumen Studio', 'Pact Health',
  'Riverstone', 'Kinetic Foundry', 'Wayfinder', 'Beacon Trust', 'Aspect AI',
  'Citrine Logistics', 'Open Field', 'Saltspring', 'Mirador', 'Linde Analytics',
];

function clamp(v: number, lo = 0, hi = 100) {
  return Math.max(lo, Math.min(hi, v));
}

function generateCell(sector: string, fn: string): HeatmapCell {
  const seed = hash(`${sector}::${fn}`);
  const rnd = mulberry32(seed);
  const base = 38 + rnd() * 36;
  const intensity = clamp(base + (SECTOR_BIAS[sector] ?? 0) * 60 + (FUNCTION_BIAS[fn] ?? 0) * 60);
  const velocity = (rnd() - 0.5) * 2 * (0.55 + (SECTOR_BIAS[sector] ?? 0));
  const oppRaw = intensity * 0.55 + (1 - Math.abs(velocity)) * 25 + (rnd() - 0.5) * 18;
  const opportunity = clamp(oppRaw);
  const companyCount = Math.round(2 + rnd() * 11);

  const dimScores = DIMENSIONS.map((d) => ({ d, s: rnd() }));
  dimScores.sort((a, b) => b.s - a.s);
  const dominantDimension = dimScores[0].d;

  const cnt = Math.min(3, companyCount);
  const topCompanies = Array.from({ length: cnt }).map((_, i) => {
    const idx = (seed + i * 17) % COMPANY_POOL.length;
    return {
      name: COMPANY_POOL[idx],
      intensity: clamp(intensity + (rnd() - 0.5) * 18),
    };
  });

  const lib = SIGNAL_LIBRARY[dominantDimension];
  const notableSignals = [lib[seed % lib.length], lib[(seed + 7) % lib.length]];

  return {
    sector,
    function: fn,
    intensity: Math.round(intensity),
    velocity: Number(velocity.toFixed(2)),
    opportunity: Math.round(opportunity),
    companyCount,
    dominantDimension,
    topCompanies,
    notableSignals,
  };
}

export const HEATMAP_CELLS: HeatmapCell[] = SECTORS.flatMap((s) =>
  FUNCTIONS.map((f) => generateCell(s.slug, f.slug)),
);

export function getCell(sector: string, fn: string): HeatmapCell | undefined {
  return HEATMAP_CELLS.find((c) => c.sector === sector && c.function === fn);
}

export type HeatmapMode = 'intensity' | 'velocity' | 'opportunity';

export function valueFor(cell: HeatmapCell, mode: HeatmapMode): number {
  if (mode === 'intensity') return cell.intensity;
  if (mode === 'velocity') return cell.velocity;
  return cell.opportunity;
}

export function getTopCells(mode: HeatmapMode, limit = 5): HeatmapCell[] {
  const sorted = [...HEATMAP_CELLS].sort((a, b) => {
    if (mode === 'velocity') return Math.abs(b.velocity) - Math.abs(a.velocity);
    return valueFor(b, mode) - valueFor(a, mode);
  });
  return sorted.slice(0, limit);
}
