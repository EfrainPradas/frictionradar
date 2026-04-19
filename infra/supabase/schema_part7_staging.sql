-- ════════════════════════════════════════════════════════════════════
-- Schema Part 7: Ingestion Staging & Import Run Tracking
--
-- Two staging tables + import run tracking for the master index
-- ingestion pipeline.
--
-- Flow: JSON file → company_staging_raw → company_staging_normalized
--       → company_master + company_aliases + company_source_records
-- ════════════════════════════════════════════════════════════════════

-- ── 1. import_runs ────────────────────────────────────────────────
-- Tracks each import execution for auditability.

CREATE TABLE IF NOT EXISTS import_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id        TEXT NOT NULL,           -- human-readable batch identifier
    source_file     TEXT NOT NULL,           -- filename or path
    source_type     TEXT NOT NULL DEFAULT 'json_file',  -- json_file, csv, api, etc.

    started_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP WITH TIME ZONE,

    total_raw       INTEGER DEFAULT 0,
    total_normalized INTEGER DEFAULT 0,
    total_inserted  INTEGER DEFAULT 0,
    total_updated   INTEGER DEFAULT 0,
    total_skipped   INTEGER DEFAULT 0,
    total_errors    INTEGER DEFAULT 0,

    status          TEXT NOT NULL DEFAULT 'running',  -- running, success, failed, partial
    error_message   TEXT,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_import_runs_batch ON import_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_import_runs_status ON import_runs(status);

-- ── 2. company_staging_raw ────────────────────────────────────────
-- Raw records exactly as they appear in the input file.

CREATE TABLE IF NOT EXISTS company_staging_raw (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    import_run_id   UUID NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,

    row_index       INTEGER NOT NULL,        -- position in input file
    raw_payload     JSONB NOT NULL,           -- original JSON object verbatim
    raw_name        TEXT,
    raw_domain      TEXT,

    status          TEXT NOT NULL DEFAULT 'pending',  -- pending, normalized, skipped, error
    error_message   TEXT,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staging_raw_run ON company_staging_raw(import_run_id);
CREATE INDEX IF NOT EXISTS idx_staging_raw_status ON company_staging_raw(status);

-- ── 3. company_staging_normalized ─────────────────────────────────
-- Cleaned, normalized records ready for upsert into company_master.

CREATE TABLE IF NOT EXISTS company_staging_normalized (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    import_run_id   UUID NOT NULL REFERENCES import_runs(id) ON DELETE CASCADE,
    staging_raw_id  UUID NOT NULL REFERENCES company_staging_raw(id) ON DELETE CASCADE,

    -- Normalized fields
    legal_name      TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    domain          TEXT,
    industry        TEXT,
    location_raw    TEXT,            -- original location string
    jurisdiction_state TEXT,         -- extracted 2-letter state code
    source          TEXT,

    -- Resolution
    matched_master_id UUID REFERENCES company_master(id) ON DELETE SET NULL,
    match_method    TEXT,             -- exact_normalized_name, exact_domain, new
    action          TEXT NOT NULL DEFAULT 'pending',  -- pending, insert, update, skip

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staging_norm_run ON company_staging_normalized(import_run_id);
CREATE INDEX IF NOT EXISTS idx_staging_norm_action ON company_staging_normalized(action);
CREATE INDEX IF NOT EXISTS idx_staging_norm_normalized ON company_staging_normalized(normalized_name);
