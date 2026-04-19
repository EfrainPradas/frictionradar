-- ════════════════════════════════════════════════════════════════════
-- Schema Part 8: Entity Resolution & Deduplication
--
-- Three tables:
--   1. company_match_candidates: pairs of potentially duplicate records
--   2. company_merge_decisions: accepted merges (canonical ← duplicate)
--   3. company_resolution_log: audit trail for every resolution run
-- ════════════════════════════════════════════════════════════════════

-- ── 1. company_match_candidates ───────────────────────────────────
-- Every candidate pair found by the resolver. May be auto-linked,
-- flagged for review, or dismissed.

CREATE TABLE IF NOT EXISTS company_match_candidates (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    master_id_a     UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,
    master_id_b     UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,

    confidence      NUMERIC(4,3) NOT NULL,  -- 0.000 – 1.000
    reason_code     TEXT NOT NULL,           -- exact_name, exact_domain, exact_ext_id, name_plus_state, fuzzy_name
    reason_detail   TEXT,                    -- human-readable explanation

    status          TEXT NOT NULL DEFAULT 'pending',  -- pending, auto_merged, confirmed, dismissed
    resolution_run_id UUID,                 -- which run found this pair

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at     TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_match_pair UNIQUE (master_id_a, master_id_b),
    CONSTRAINT ck_pair_order CHECK (master_id_a < master_id_b)  -- canonical ordering
);

CREATE INDEX IF NOT EXISTS idx_match_candidates_status ON company_match_candidates(status);
CREATE INDEX IF NOT EXISTS idx_match_candidates_confidence ON company_match_candidates(confidence);
CREATE INDEX IF NOT EXISTS idx_match_candidates_a ON company_match_candidates(master_id_a);
CREATE INDEX IF NOT EXISTS idx_match_candidates_b ON company_match_candidates(master_id_b);

-- ── 2. company_merge_decisions ────────────────────────────────────
-- Accepted merges: canonical record absorbs the duplicate.
-- The duplicate is marked entity_status='merged' and points here.

CREATE TABLE IF NOT EXISTS company_merge_decisions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_id    UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,
    duplicate_id    UUID NOT NULL REFERENCES company_master(id) ON DELETE CASCADE,
    match_candidate_id UUID REFERENCES company_match_candidates(id) ON DELETE SET NULL,

    merge_reason    TEXT NOT NULL,
    confidence      NUMERIC(4,3) NOT NULL,
    merged_by       TEXT NOT NULL DEFAULT 'auto',  -- auto, manual

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(canonical_id, duplicate_id)
);

CREATE INDEX IF NOT EXISTS idx_merge_canonical ON company_merge_decisions(canonical_id);
CREATE INDEX IF NOT EXISTS idx_merge_duplicate ON company_merge_decisions(duplicate_id);

-- ── 3. company_resolution_log ─────────────────────────────────────
-- Audit trail: one row per resolution run.

CREATE TABLE IF NOT EXISTS company_resolution_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    started_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP WITH TIME ZONE,

    total_compared  INTEGER DEFAULT 0,
    total_candidates INTEGER DEFAULT 0,
    total_auto_merged INTEGER DEFAULT 0,
    total_flagged   INTEGER DEFAULT 0,

    status          TEXT NOT NULL DEFAULT 'running',
    error_message   TEXT,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
