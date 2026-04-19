-- ============================================================
-- Friction Radar — Extraction Routing Tables (Phase 1)
-- ============================================================
-- Three tables for the new extraction routing layer:
--   1. company_ats_detection    — which ATS was detected per company
--   2. company_extraction_cache — cached extraction results
--   3. company_extraction_attempts — audit log of every attempt
-- ============================================================

-- 1. ATS Detection
CREATE TABLE IF NOT EXISTS company_ats_detection (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    ats_platform TEXT NOT NULL,
    ats_url TEXT,
    detection_source TEXT,
    confidence NUMERIC,
    detected_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ats_detection_company
    ON company_ats_detection(company_id);
CREATE INDEX IF NOT EXISTS idx_ats_detection_domain
    ON company_ats_detection(domain);

-- 2. Extraction Cache
CREATE TABLE IF NOT EXISTS company_extraction_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    strategy_used TEXT NOT NULL,
    careers_url TEXT,
    ats_platform TEXT,
    open_positions_count INTEGER,
    jobs_count INTEGER DEFAULT 0,
    hiring_areas_json JSONB,
    jobs_json JSONB,
    evidence_quality TEXT,
    confidence NUMERIC,
    cached_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_extraction_cache_company
    ON company_extraction_cache(company_id);
CREATE INDEX IF NOT EXISTS idx_extraction_cache_domain
    ON company_extraction_cache(domain);

-- 3. Extraction Attempts (audit log)
CREATE TABLE IF NOT EXISTS company_extraction_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    strategy TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    fallback_from TEXT,
    success BOOLEAN DEFAULT false,
    error TEXT,
    jobs_found INTEGER DEFAULT 0,
    positions_count INTEGER,
    evidence_quality TEXT,
    duration_ms INTEGER DEFAULT 0,
    used_cache BOOLEAN DEFAULT false,
    careers_url TEXT,
    ats_platform TEXT,
    attempted_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extraction_attempts_company
    ON company_extraction_attempts(company_id);
CREATE INDEX IF NOT EXISTS idx_extraction_attempts_domain
    ON company_extraction_attempts(domain);
CREATE INDEX IF NOT EXISTS idx_extraction_attempts_strategy
    ON company_extraction_attempts(strategy);
