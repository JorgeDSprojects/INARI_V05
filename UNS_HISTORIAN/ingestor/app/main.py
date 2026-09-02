# UNS_HISTORIAN/ingestor/app/main.py
"""Entrypoint: connects to Postgres and EMQX, warms the dedup cache, subscribes
to MQTT_TOPIC_FILTER, and flushes buffered rows every FLUSH_INTERVAL_SECONDS
or as soon as the buffer reaches FLUSH_MAX_ROWS, whichever comes first.

See docs/superpowers/specs/2026-09-02-uns-historian-design.md, Section 3.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg

from app.buffer import FlushBuffer
from app.config import Settings, load_settings
from app.db import insert_batch, load_last_values
from app.dedup import DedupCache
from app.handler import handle_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("uns_historian.ingestor")


def _flush_loop(
    stop_event: threading.Event,
    flush_requested: threading.Event,
    settings: Settings,
    buffer: FlushBuffer,
) -> None:
    conn = psycopg.connect(settings.database_url, autocommit=False)
    try:
        while not stop_event.is_set():
            flush_requested.wait(settings.flush_interval_seconds)
            flush_requested.clear()
            rows = buffer.drain()
            if rows:
                try:
                    inserted = insert_batch(conn, rows)
                    logger.info("Flushed %d row(s)", inserted)
                except psycopg.Error:
                    logger.exception("Flush failed, reconnecting and retrying next cycle")
                    conn.close()
                    conn = psycopg.connect(settings.database_url, autocommit=False)
            dropped = buffer.pop_dropped_count()
            if dropped:
                logger.warning("Dropped %d oldest row(s): buffer was full", dropped)
    finally:
        conn.close()


def main() -> None:
    settings = load_settings()

    warm_conn = psycopg.connect(settings.database_url)
    try:
        initial_cache = load_last_values(warm_conn)
    finally:
        warm_conn.close()
    logger.info("Warmed dedup cache with %d topic(s)", len(initial_cache))

    cache = DedupCache(initial=initial_cache)
    buffer = FlushBuffer(max_rows=settings.buffer_max_rows)

    stop_event = threading.Event()
    flush_requested = threading.Event()
    flush_thread = threading.Thread(
        target=_flush_loop, args=(stop_event, flush_requested, settings, buffer), daemon=True
    )
    flush_thread.start()

    def on_connect(client, userdata, connect_flags, reason_code, properties):
        logger.info("Connected to EMQX (reason_code=%s)", reason_code)
        client.subscribe(settings.mqtt_topic_filter, qos=1)

    def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("Disconnected from EMQX (reason_code=%s)", reason_code)

    def on_message(client, userdata, message):
        arrival_time = datetime.now(timezone.utc)
        handle_message(
            message.topic,
            message.payload,
            message.qos,
            message.retain,
            arrival_time,
            cache,
            buffer,
        )
        if len(buffer) >= settings.flush_max_rows:
            flush_requested.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        protocol=mqtt.MQTTv5,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    client.connect(settings.emqx_host, settings.emqx_port, keepalive=60)
    try:
        client.loop_forever()
    finally:
        stop_event.set()
        flush_thread.join(timeout=settings.flush_interval_seconds + 5)


if __name__ == "__main__":
    main()
