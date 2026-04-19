-- ════════════════════════════════════════════════════════════════════
-- Schema Part 6: U.S. Company Master Index
--
-- Canonical data model for FrictionRadar's company input layer.
-- Supports entity resolution, external identifiers, aliases, and
-- full source provenance tracking.
--
-- Design decisions:
--   1. company_master is SEPARATE from existing "companies" table.
--      The current companies table is the analysis workspace;
--      company_master is the authoritative identity registry.
--      They'll be linked via domain resolution in Phase 2+.
--   2. External IDs are stored in a flexible EAV-style table so we
--      can add new identifier types (D-U-N-S, LEI, etc.) without DDL.
--   3. EIN is just another external ID (id_type = 'ein'), not a
--      first-class column — stored only as optional secondary identifier.
--   4. Source records keep raw payload as JSONB so we never lose
--      provenance even if parsing logic changes.
-- ════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── 1. company_master ─────────────────────────────────────────────
-- Canonical identity record for each legal entity.

CREATE TABLE IF NOT EXISTS company_master (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Names
    legal_name      TEXT NOT NULL,
    normalized_name TEXT NOT NULL,  -- lowercase, stripped punctuation

    -- Entity metadata
    entity_type     TEXT,           -- corporation, llc, lp, sole_prop, nonprofit, etc.
    entity_status   TEXT NOT NULL DEFAULT 'active',  -- active, inactive, dissolved, merged, unknown
    jurisdiction_state TEXT,        -- 2-letter US state code (DE, CA, etc.)
    formation_date  DATE,

    -- Source quality
    source_priority  INTEGER NOT NULL DEFAULT 50,  -- 0=highest priority, 100=lowest
    source_confidence NUMERIC(3,2) NOT NULL DEFAULT 0.50,  -- 0.00 – 1.00

    -- Linking (populated in later phases)
    linked_company_id UUID REFERENCES companies(id) ON DELETE SET NULL,

    -- Verification
    last_verified_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_company_master_normalized_name ON company_master(normalized_name);
CREATE INDEX IF NOT EXISTS idx_company_master_legal_name ON company_master(legal_name);
CREATE INDEX IF NOT EXISTS idx_company_master_entity_status ON company_master(entity_status);
CREATE INDEX IF NOT EXISTS idx_company_master_jurisdiction ON company_master(jurisdiction_state);
CREATE INDEX IF NOT EXISTS idx_company_master_linked_company ON company_master(linked_company_id);

-- ── 2. company_external_ids ───────────────────────────────────────
-- Flexible external identifier storage. One row per (company, id_type).
-- Supports: state_registry_id, ein, edgar_cik, sam_uei, duns, lei, etc.

CREATE TABLE IF NOT EXISTS company_external_ids (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_master_id UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,

    id_type         TEXT NOT NULL,  -- state_registry_id, ein, edgar_cik, sam_uei, duns, lei
    id_value        TEXT NOT NULL,
    issuing_authority TEXT,         -- e.g. 'DE_SOS', 'IRS', 'SEC', 'GSA'
    verified        BOOLEAN DEFAULT FALSE,
    verified_at     TIMESTAMP WITH TIME ZONE,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_master_id, id_type, id_value)
);

CREATE INDEX IF NOT EXISTS idx_company_external_ids_master ON company_external_ids(company_master_id);
CREATE INDEX IF NOT EXISTS idx_company_external_ids_type_value ON company_external_ids(id_type, id_value);

-- ── 3. company_aliases ────────────────────────────────────────────
-- DBA names, trade names, abbreviations, normalized variants.

CREATE TABLE IF NOT EXISTS company_aliases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_master_id UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,

    alias_name      TEXT NOT NULL,
    alias_type      TEXT NOT NULL DEFAULT 'dba',  -- dba, trade_name, abbreviation, former_name, normalized
    is_primary      BOOLEAN DEFAULT FALSE,
    source          TEXT,           -- which source provided this alias

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_master_id, alias_name, alias_type)
);

CREATE INDEX IF NOT EXISTS idx_company_aliases_master ON company_aliases(company_master_id);
CREATE INDEX IF NOT EXISTS idx_company_aliases_name ON company_aliases(alias_name);

-- ── 4. company_source_records ─────────────────────────────────────
-- Full provenance: which source produced each record, when, and the
-- raw payload. Never delete source records — they're the audit trail.

CREATE TABLE IF NOT EXISTS company_source_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_master_id UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,

    source_name     TEXT NOT NULL,  -- 'sec_edgar', 'sam_gov', 'state_sos_de', 'csv_import', etc.
    source_record_id TEXT,          -- ID from the external source (CIK, UEI, filing number)
    source_url      TEXT,           -- URL where data was fetched

    fetched_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_payload     JSONB,          -- full response from source, for reprocessing

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_company_source_records_master ON company_source_records(company_master_id);
CREATE INDEX IF NOT EXISTS idx_company_source_records_source ON company_source_records(source_name);
CREATE INDEX IF NOT EXISTS idx_company_source_records_source_id ON company_source_records(source_name, source_record_id);
