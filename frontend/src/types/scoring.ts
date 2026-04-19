export type FrictionCategory =
  | 'reporting_fragmentation'
  | 'process_inefficiency'
  | 'tooling_inconsistency'
  | 'scaling_strain'
  | 'customer_experience_friction';

export interface CategoryBreakdown {
  score: number;
  matched_signals: string[];
}

export type ScoringBreakdown = Record<FrictionCategory, CategoryBreakdown>;

export interface FrictionScore {
  id: string;
  company_id: string;
  total_score: number;
  dominant_friction_type: FrictionCategory;
  scoring_breakdown_json: ScoringBreakdown;
  scoring_version: string | null;
  computed_at: string;
  created_at: string;
  open_positions_count?: number | null;
}
