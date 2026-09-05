-- UNS_HISTORIAN/postgres/init.sql
-- UNS Historian schema — generic MQTT message capture.
-- See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 2.
-- `id` added for UNS_SILVER's watermark-based consumption — see
-- UNS_SILVER/docs/superpowers/specs/2026-09-05-uns-silver-design.md, Section 1.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS mqtt_messages (
    id           BIGSERIAL,
    time         TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,
    payload      JSONB,
    raw_payload  TEXT,
    qos          SMALLINT NOT NULL,
    retain       BOOLEAN NOT NULL
);

SELECT create_hypertable('mqtt_messages', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_mqtt_messages_topic_time ON mqtt_messages (topic, time DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_messages_id ON mqtt_messages (id);
