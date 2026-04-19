-- ════════════════════════════════════════════════════════════════════
-- Schema Part 9: Company Web Presence / Domain Resolution
--
-- Tracks the official web presence of each company in the master index.
-- One company may have multiple domains (primary + alternates).
-- Designed to feed downstream careers discovery and ATS detection.
--
-- Resolution statuses:
--   unresolved  — no domain attempt yet
--   resolved    — confirmed working domain
--   ambiguous   — multiple candidates, needs review
--   rejected    — domain checked and found invalid/unrelated
--   redirect    — domain redirects to another (stored in redirects_to)
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS company_domains (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_master_id UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,

    domain            TEXT NOT NULL,             -- e.g. "stripe.com"
    is_primary        BOOLEAN NOT NULL DEFAULT FALSE,
    domain_status     TEXT NOT NULL DEFAULT 'unresolved',  -- unresolved, resolved, ambiguous, rejected, redirect
    confidence        NUMERIC(4,3) NOT NULL DEFAULT 0.500,

    -- Discovery metadata
    source            TEXT,                      -- json_import, homepage_scan, manual, etc.
    http_status       INTEGER,                   -- last HTTP status code
    redirects_to      TEXT,                      -- if status=redirect, where it goes
    title_tag         TEXT,                      -- <title> from homepage

    -- Verification
    last_checked_at   TIMESTAMP WITH TIME ZONE,
    last_verified_at  TIMESTAMP WITH TIME ZONE,  -- last time confirmed alive + matching

    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_master_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_company_domains_master ON company_domains(company_master_id);
CREATE INDEX IF NOT EXISTS idx_company_domains_domain ON company_domains(domain);
CREATE INDEX IF NOT EXISTS idx_company_domains_status ON company_domains(domain_status);
CREATE INDEX IF NOT EXISTS idx_company_domains_primary ON company_domains(is_primary) WHERE is_primary = TRUE;

-- ── domain_resolution_runs ────────────────────────────────────────
-- Audit trail: one row per resolution batch execution.

CREATE TABLE IF NOT EXISTS domain_resolution_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP WITH TIME ZONE,

    total_processed INTEGER DEFAULT 0,
    total_resolved  INTEGER DEFAULT 0,
    total_rejected  INTEGER DEFAULT 0,
    total_ambiguous INTEGER DEFAULT 0,
    total_errors    INTEGER DEFAULT 0,

    status          TEXT NOT NULL DEFAULT 'running',
    error_message   TEXT,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
