-- ════════════════════════════════════════════════════════════════════
-- Schema Part 10: Downstream Input View
--
-- Materialized view that produces the working input dataset for
-- FrictionRadar's downstream pipeline (careers discovery, ATS
-- detection, scoring).
--
-- Joins company_master + company_domains + company_external_ids
-- into a single flat row per company with readiness flags.
-- ════════════════════════════════════════════════════════════════════

-- Drop existing view if refreshing schema
DROP VIEW IF EXISTS v_downstream_input;

CREATE OR REPLACE VIEW v_downstream_input AS
WITH primary_domains AS (
    SELECT
        company_master_id,
        domain,
        domain_status,
        confidence AS domain_confidence,
        http_status,
        title_tag,
        last_verified_at AS domain_verified_at
    FROM company_domains
    WHERE is_primary = TRUE
),
ext_ids_agg AS (
    SELECT
        company_master_id,
        jsonb_object_agg(id_type, id_value) AS external_ids,
        count(*) AS external_id_count
    FROM company_external_ids
    GROUP BY company_master_id
)
SELECT
    m.id                    AS company_id,
    m.legal_name,
    m.normalized_name,
    m.entity_type,
    m.entity_status,
    m.jurisdiction_state,
    m.formation_date,
    m.source_priority,
    m.source_confidence,
    m.last_verified_at,
    m.linked_company_id,

    -- Domain
    d.domain                AS primary_domain,
    CASE WHEN d.domain IS NOT NULL
         THEN 'https://' || d.domain
         ELSE NULL
    END                     AS official_website,
    d.domain_status,
    d.domain_confidence,
    d.http_status           AS domain_http_status,
    d.title_tag             AS domain_title,
    d.domain_verified_at,

    -- External IDs (flat JSON + count)
    COALESCE(e.external_ids, '{}'::jsonb) AS external_ids,
    COALESCE(e.external_id_count, 0)      AS external_id_count,

    -- ── Readiness flags ───────────────────────────────────────
    CASE
        WHEN m.entity_status = 'merged' THEN 'merged'
        WHEN d.domain IS NOT NULL AND d.domain_status = 'resolved'
            THEN 'ready_for_careers_discovery'
        WHEN d.domain IS NOT NULL AND d.domain_status IN ('unresolved', 'ambiguous')
            THEN 'ready_for_domain_resolution'
        WHEN d.domain IS NULL
            THEN 'needs_domain'
        ELSE 'needs_review'
    END                     AS readiness_status,

    -- Boolean convenience flags
    (d.domain IS NOT NULL AND d.domain_status = 'resolved')
                            AS has_resolved_domain,
    (e.external_id_count IS NOT NULL AND e.external_id_count > 0)
                            AS has_external_ids,
    (m.source_confidence >= 0.70)
                            AS high_confidence,

    m.created_at,
    m.updated_at

FROM company_master m
LEFT JOIN primary_domains d ON d.company_master_id = m.id
LEFT JOIN ext_ids_agg e ON e.company_master_id = m.id
WHERE m.entity_status != 'merged';
