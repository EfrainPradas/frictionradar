export interface TaxonItem {
  slug: string;
  label: string;
}

export const SECTORS: TaxonItem[] = [
  { slug: 'software-saas', label: 'Software & SaaS' },
  { slug: 'ai-ml', label: 'AI & Machine Learning' },
  { slug: 'fintech', label: 'Fintech' },
  { slug: 'healthcare-biotech', label: 'Healthcare & Biotech' },
  { slug: 'retail', label: 'Retail' },
  { slug: 'logistics', label: 'Logistics' },
  { slug: 'cybersecurity', label: 'Cybersecurity' },
  { slug: 'media', label: 'Media' },
  { slug: 'manufacturing', label: 'Manufacturing' },
  { slug: 'finance', label: 'Finance' },
];

export const FUNCTIONS: TaxonItem[] = [
  { slug: 'engineering', label: 'Engineering' },
  { slug: 'product', label: 'Product' },
  { slug: 'analytics', label: 'Analytics' },
  { slug: 'it', label: 'IT' },
  { slug: 'sales', label: 'Sales' },
  { slug: 'marketing', label: 'Marketing' },
  { slug: 'support', label: 'Customer Support' },
  { slug: 'operations', label: 'Operations' },
  { slug: 'supply-chain', label: 'Supply Chain' },
  { slug: 'finance', label: 'Finance' },
  { slug: 'people', label: 'HR / People' },
  { slug: 'recruiting', label: 'Recruiting' },
  { slug: 'legal', label: 'Legal' },
];

export type SectorSlug = (typeof SECTORS)[number]['slug'];
export type FunctionSlug = (typeof FUNCTIONS)[number]['slug'];

export const RADAR_DIMENSIONS = [
  { slug: 'reporting', label: 'Reporting' },
  { slug: 'process', label: 'Process' },
  { slug: 'tooling', label: 'Tooling' },
  { slug: 'scaling', label: 'Scaling' },
  { slug: 'cx', label: 'CX' },
] as const;
