from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from app.config import settings

logger = logging.getLogger(__name__)

_client: mqtt.Client | None = None


def get_mqtt_client() -> mqtt.Client:
    global _client
    if _client is None or not _client.is_connected():
        _client = mqtt.Client(client_id=settings.emqx_client_id, protocol=mqtt.MQTTv5)
        _client.connect(settings.emqx_host, settings.emqx_port, keepalive=60)
        _client.loop_start()
    return _client


def publish_descriptive(topic: str, payload: dict[str, Any]) -> None:
    client = get_mqtt_client()
    message = json.dumps(payload, ensure_ascii=False, default=str)
    result = client.publish(topic, message, qos=1, retain=True)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        logger.error("MQTT publish failed rc=%s topic=%s", result.rc, topic)
    else:
        logger.info("Published _descriptive to %s", topic)


def clear_retained(topic: str) -> None:
    """Clear a retained MQTT message by publishing an empty payload to the same topic."""
    client = get_mqtt_client()
    result = client.publish(topic, payload=None, qos=1, retain=True)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        logger.error("MQTT clear_retained failed rc=%s topic=%s", result.rc, topic)
    else:
        logger.info("Cleared retained %s", topic)


def disconnect_mqtt() -> None:
    global _client
    if _client:
        _client.loop_stop()
        _client.disconnect()
        _client = None
