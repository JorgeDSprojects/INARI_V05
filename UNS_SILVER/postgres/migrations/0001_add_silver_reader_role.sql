-- UNS_SILVER/postgres/migrations/0001_add_silver_reader_role.sql
-- Additive, idempotent. Apply to an already-running instance with:
--   docker exec -i uns_silver_postgres psql -U silver -d uns_silver \
--     < postgres/migrations/0001_add_silver_reader_role.sql
-- Requires SILVER_READER_PASSWORD to already be set in the container's
-- environment (Step 1 of this task). New instances get this from
-- init.sql on first boot instead.
\set silver_reader_password `echo "$SILVER_READER_PASSWORD"`

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'silver_reader') THEN
        CREATE ROLE silver_reader WITH LOGIN PASSWORD :'silver_reader_password';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE uns_silver TO silver_reader;
GRANT USAGE ON SCHEMA public TO silver_reader;
GRANT SELECT ON signal_catalog, silver_readings, silver_events, silver_latest_value,
                silver_readings_1m, silver_readings_1h TO silver_reader;
