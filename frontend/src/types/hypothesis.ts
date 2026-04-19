import type { FrictionCategory } from './scoring';

export interface OpportunityHypothesis {
  id: string;
  company_id: string;
  friction_score_id: string | null;
  summary: string;
  friction_type: FrictionCategory;
  suggested_opportunity: string;
  rationale_json: {
    top_signals: string[];
    top_categories: string[];
    total_score: number;
    scoring_version: string | null;
  } | null;
  llm_confidence: number | null;
  created_at: string;
}
