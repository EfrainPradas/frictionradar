-- ════════════════════════════════════════════════════════════════════
-- Schema Part 11: Raw Acquisition Log
--
-- Tracks every raw source file downloaded from external registries.
-- No parsing or company import happens here — just acquisition.
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS raw_acquisition_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    source_name     TEXT NOT NULL,           -- e.g. "florida_dos"
    artifact_name   TEXT NOT NULL,           -- e.g. "corp_20260414.txt"
    artifact_type   TEXT NOT NULL DEFAULT 'fixed_width',  -- fixed_width, csv, json, xml

    -- Download metadata
    downloaded_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    file_size_bytes BIGINT,
    sha256          TEXT,                    -- hex-encoded SHA-256 checksum
    local_path      TEXT,                    -- where the raw file is stored

    -- Status
    status          TEXT NOT NULL DEFAULT 'completed',  -- downloading, completed, failed, duplicate
    error_message   TEXT,

    -- Batch
    batch_id        TEXT,                    -- optional grouping

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_acquisition_source ON raw_acquisition_log(source_name);
CREATE INDEX IF NOT EXISTS idx_acquisition_sha256 ON raw_acquisition_log(sha256);
CREATE INDEX IF NOT EXISTS idx_acquisition_status ON raw_acquisition_log(status);
