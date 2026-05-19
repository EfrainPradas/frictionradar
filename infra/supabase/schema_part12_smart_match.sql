-- ════════════════════════════════════════════════════════════════════
-- Schema Part 12: Smart-Match Cache (pain-matching denormalized layer)
--
-- Materialized snapshot of each company's current pain verdict + a
-- pgvector embedding of that pain. Refreshed nightly by
-- backend/scripts/nightly_smart_match_refresh.py.
--
-- This is the single source consumed by /internal/v1/match to rank
-- FrictionRadar's company universe against a candidate payload.
-- ════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS smart_match_cache (
    company_id              UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    domain                  TEXT NOT NULL,

    -- Verdict snapshot (denormalized from final_verdict_engine + friction_score)
    friction_score          NUMERIC,
    dominant_friction_type  TEXT,
    diagnostic_state        TEXT,
    main_pain               TEXT,
    where_pain_lives        TEXT,
    what_the_company_needs  TEXT,
    best_attack_angle       TEXT,

    -- Eligibility (from positioning_engine.is_company_positioning_eligible)
    confidence              TEXT,              -- high | moderate | low
    eligibility_gate        TEXT,              -- full | conditional | none

    -- Full KPI payload for debugging / operator review
    evaluation_kpis         JSONB,
    inferred_sector         TEXT,

    -- OpenAI text-embedding-3-small dimension
    pain_embedding          vector(1536),

    refreshed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    refresh_run_id          TEXT
);

CREATE INDEX IF NOT EXISTS idx_smart_match_cache_domain
    ON smart_match_cache (LOWER(domain));
CREATE INDEX IF NOT EXISTS idx_smart_match_cache_eligibility
    ON smart_match_cache (eligibility_gate);
CREATE INDEX IF NOT EXISTS idx_smart_match_cache_sector
    ON smart_match_cache (inferred_sector);

-- ivfflat for cosine similarity. Target 'lists' = sqrt(rows); 100 is fine
-- up to ~10k rows. Re-tune when catalogue grows past that.
CREATE INDEX IF NOT EXISTS idx_smart_match_cache_embedding
    ON smart_match_cache
    USING ivfflat (pain_embedding vector_cosine_ops) WITH (lists = 100);
