-- Friction Radar - Part 3: Intelligence Layer Schema Additions
-- Run this AFTER the Part 2 schema

-- Drop placeholder stubs and recreate with full structure
DROP TABLE IF EXISTS opportunity_hypotheses;
DROP TABLE IF EXISTS friction_scores;

CREATE TABLE friction_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    total_score NUMERIC NOT NULL,
    dominant_friction_type TEXT NOT NULL,
    scoring_breakdown_json JSONB NOT NULL,
    scoring_version TEXT,
    computed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_friction_scores_company_id ON friction_scores(company_id);
CREATE INDEX idx_friction_scores_dominant_type ON friction_scores(dominant_friction_type);
CREATE INDEX idx_friction_scores_computed_at ON friction_scores(computed_at);

CREATE TABLE opportunity_hypotheses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    friction_score_id UUID REFERENCES friction_scores(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    friction_type TEXT NOT NULL,
    suggested_opportunity TEXT NOT NULL,
    rationale_json JSONB,
    llm_confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_opportunity_hypotheses_company_id ON opportunity_hypotheses(company_id);
CREATE INDEX idx_opportunity_hypotheses_friction_type ON opportunity_hypotheses(friction_type);
CREATE INDEX idx_opportunity_hypotheses_created_at ON opportunity_hypotheses(created_at);
