"""Entrypoint: subscribes to EMQX with a persistent session, filters
`_informative`/`_analytical` topics, and XADDs each reading to its per-topic Redis Stream.

See docs/superpowers/specs/2026-09-03-uns-dashboard-design.md, Section 3.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import redis

from app.config import load_settings
from app.filter import is_bridgeable_topic
from app.stream_writer import build_fields, stream_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("uns_dashboard.bridge")


def main() -> None:
    settings = load_settings()
    redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)

    def on_connect(client, userdata, connect_flags, reason_code, properties):
        logger.info("Connected to EMQX (reason_code=%s)", reason_code)
        client.subscribe("#", qos=1)

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from EMQX (reason_code=%s)", reason_code)

    def on_message(client, userdata, message):
        if not is_bridgeable_topic(message.topic):
            return
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Skipping non-JSON payload on %s", message.topic)
            return
        arrival_iso = datetime.now(timezone.utc).isoformat()
        fields = build_fields(payload, arrival_iso)
        try:
            redis_client.xadd(stream_key(message.topic), fields, maxlen=settings.stream_maxlen, approximate=True)
        except redis.RedisError:
            logger.exception("Failed to XADD reading for %s", message.topic)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.connect(settings.emqx_host, settings.emqx_port, keepalive=60, clean_start=False)
    client.loop_forever()


if __name__ == "__main__":
    main()
