-- Migration 004: Add risk_events table
-- Date: 2026-01-29
-- Reason: Persist decision contract evaluations from risk service

CREATE TABLE risk_events (
    id SERIAL PRIMARY KEY,
    timestamp_ms BIGINT NOT NULL,
    symbol VARCHAR(50),
    decision VARCHAR(10) NOT NULL,
    reason_code VARCHAR(10),
    contract_version VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX idx_risk_events_timestamp ON risk_events(timestamp_ms);
CREATE INDEX idx_risk_events_symbol ON risk_events(symbol);

COMMENT ON TABLE risk_events IS 'Risk decision events (Decision Contract v1)';
COMMENT ON COLUMN risk_events.payload IS 'Full risk_event payload (JSON)';

INSERT INTO schema_version (version, description) VALUES
    ('1.0.3', 'Add risk_events table for decision contract v1');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'risk_events'
    ) THEN
        RAISE EXCEPTION 'Migration failed: risk_events table missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'risk_events'
        AND indexname = 'idx_risk_events_timestamp'
    ) THEN
        RAISE EXCEPTION 'Migration failed: idx_risk_events_timestamp index missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'risk_events'
        AND indexname = 'idx_risk_events_symbol'
    ) THEN
        RAISE EXCEPTION 'Migration failed: idx_risk_events_symbol index missing';
    END IF;

    RAISE NOTICE 'Migration 004 successful: risk_events table created';
END $$;
