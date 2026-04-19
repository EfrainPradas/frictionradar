-- Fix schema: add missing tables for job roles, role signals, and hiring patterns
-- Run this against your Supabase DB to create the missing tables

-- company_job_roles: stores individual job listings found on careers pages
CREATE TABLE IF NOT EXISTS company_job_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source_url TEXT,
    role_title TEXT NOT NULL,
    role_location TEXT,
    role_department TEXT,
    role_description TEXT,
    functional_area TEXT,
    functional_area_confidence TEXT,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_company_job_roles_company_id ON company_job_roles(company_id);
CREATE INDEX IF NOT EXISTS idx_company_job_roles_functional_area ON company_job_roles(functional_area);

-- company_role_signals: per-role signal annotations
CREATE TABLE IF NOT EXISTS company_role_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    job_role_id UUID REFERENCES company_job_roles(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL,
    signal_text TEXT NOT NULL,
    functional_area TEXT,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_company_role_signals_company_id ON company_role_signals(company_id);
CREATE INDEX IF NOT EXISTS idx_company_role_signals_job_role_id ON company_role_signals(job_role_id);

-- hiring_patterns: aggregated hiring pattern analysis per company
CREATE TABLE IF NOT EXISTS hiring_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    top_functional_areas TEXT,
    top_capability_themes TEXT,
    total_roles_found NUMERIC DEFAULT 0,
    unique_functions_found NUMERIC DEFAULT 0,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hiring_patterns_company_id ON hiring_patterns(company_id);

-- Add missing columns to opportunity_hypotheses if not present
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'opportunity_hypotheses' AND column_name = 'open_positions_count') THEN
        ALTER TABLE opportunity_hypotheses ADD COLUMN open_positions_count NUMERIC;
    END IF;
END $$;

-- Add open_positions_count to friction_scores if missing
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'friction_scores' AND column_name = 'open_positions_count') THEN
        ALTER TABLE friction_scores ADD COLUMN open_positions_count NUMERIC;
    END IF;
END $$;
