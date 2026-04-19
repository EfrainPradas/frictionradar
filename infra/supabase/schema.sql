-- Schema for Friction Radar MVP - Part 2

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    domain TEXT UNIQUE,
    industry TEXT,
    company_size TEXT,
    source_added_from TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE company_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_url TEXT,
    signal_type TEXT NOT NULL,
    signal_text TEXT NOT NULL,
    numeric_value NUMERIC,
    confidence NUMERIC,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_company_signals_company_id ON company_signals(company_id);
CREATE INDEX idx_company_signals_source_type ON company_signals(source_type);
CREATE INDEX idx_company_signals_signal_type ON company_signals(signal_type);

CREATE TABLE collection_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    collector_type TEXT NOT NULL,
    status TEXT NOT NULL, -- pending, running, completed, failed
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata_json JSONB
);

CREATE TABLE review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    review_status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected
    reviewer_notes TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Placeholders for future implementaton
CREATE TABLE IF NOT EXISTS friction_scores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    total_score NUMERIC NOT NULL DEFAULT 0,
    dominant_friction_type TEXT NOT NULL DEFAULT 'scaling_strain',
    scoring_breakdown_json JSONB NOT NULL DEFAULT '{}',
    scoring_version TEXT,
    open_positions_count NUMERIC,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_friction_scores_company_id ON friction_scores(company_id);
CREATE INDEX IF NOT EXISTS idx_friction_scores_computed_at ON friction_scores(computed_at);
CREATE INDEX IF NOT EXISTS idx_friction_scores_dominant_friction_type ON friction_scores(dominant_friction_type);

CREATE TABLE opportunity_hypotheses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    hypothesis_text TEXT,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
