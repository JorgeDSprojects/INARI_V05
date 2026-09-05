-- UNS_HISTORIAN/postgres/migrations/0001_add_silver_support.sql
-- Additive, idempotent. Apply to an already-running instance with:
--   docker compose exec -T historian_postgres psql -U historian -d uns_historian \
--     < postgres/migrations/0001_add_silver_support.sql
-- New instances get this from init.sql on first boot instead; running this
-- again there is a harmless no-op.
--
-- Not declared PRIMARY KEY: TimescaleDB requires a hypertable's unique/
-- primary-key constraints to include the partitioning column (`time`), and
-- a plain monotonic sequence + index is all a watermark cursor needs.
ALTER TABLE mqtt_messages ADD COLUMN IF NOT EXISTS id BIGSERIAL;
CREATE INDEX IF NOT EXISTS idx_mqtt_messages_id ON mqtt_messages (id);
