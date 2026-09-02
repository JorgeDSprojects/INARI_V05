from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from typing import Any

import httpx
import paho.mqtt.client as mqtt

from app.models.broker import Broker


def _api_base(broker: Broker) -> str:
    scheme = "https" if broker.use_tls else "http"
    return f"{scheme}://{broker.host}:{broker.api_port}/api/v5"


def _auth(broker: Broker) -> tuple[str, str] | None:
    if broker.username:
        return (broker.username, broker.password or "")
    return None


async def get_broker_status(broker: Broker) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_api_base(broker)}/status",
                auth=_auth(broker),
            )
            r.raise_for_status()
            data = r.json()
            return {
                "connected": True,
                "version": data.get("emqx_version"),
                "node": data.get("node"),
                "error": None,
            }
    except Exception as exc:
        return {"connected": False, "version": None, "node": None, "error": str(exc)}


async def test_broker_connection(broker: Broker) -> dict[str, Any]:
    connected_event = asyncio.Event()
    error_msg: list[str] = []

    def on_connect(client: mqtt.Client, userdata: Any, flags: Any, rc: int, properties: Any = None) -> None:
        if rc == 0:
            connected_event.set()
        else:
            error_msg.append(f"rc={rc}")

    client = mqtt.Client(client_id="uns_manager_test_probe", protocol=mqtt.MQTTv5)
    if broker.username:
        client.username_pw_set(broker.username, broker.password or "")
    client.on_connect = on_connect

    start = time.monotonic()
    try:
        client.connect(broker.host, broker.port, keepalive=10)
        client.loop_start()
        try:
            await asyncio.wait_for(connected_event.wait(), timeout=5.0)
            latency_ms = int((time.monotonic() - start) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "error": None}
        except asyncio.TimeoutError:
            msg = error_msg[0] if error_msg else "Connection timed out"
            return {"ok": False, "latency_ms": None, "error": msg}
    except Exception as exc:
        return {"ok": False, "latency_ms": None, "error": str(exc)}
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass


async def get_subscriptions(broker: Broker, topic: str) -> list[dict[str, Any]]:
    """Return active EMQX subscribers for a topic. Returns [] on any error."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_api_base(broker)}/subscriptions",
                params={"topic": topic},
                auth=_auth(broker),
            )
            r.raise_for_status()
            data = r.json()
            items: list[Any] = data.get("data", data) if isinstance(data, dict) else data
            return [
                {
                    "client_id": item.get("clientid", ""),
                    "topic_filter": item.get("topic", topic),
                    "qos": item.get("qos", 0),
                    "connected_at": None,
                }
                for item in items
            ]
    except Exception:
        return []


async def list_retained_topics_by_prefix(broker: Broker, prefix: str) -> list[str]:
    """List all retained MQTT topics whose path starts with *prefix* (i.e. prefix/#).
    Uses EMQX retainer API. Returns [] on any error."""
    filter_topic = f"{prefix}/#"
    topics: list[str] = []
    page = 1
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{_api_base(broker)}/retainer/messages",
                    params={"topic": filter_topic, "page": page, "limit": 1000},
                    auth=_auth(broker),
                )
                if r.status_code != 200:
                    break
                data = r.json()
                items: list[Any] = data.get("data", data) if isinstance(data, dict) else data
                if not items:
                    break
                for item in items:
                    if t := item.get("topic"):
                        topics.append(t)
                if len(items) < 1000:
                    break
                page += 1
        except Exception:
            break
    return topics


async def get_retained_payload(broker: Broker, topic: str) -> dict[str, Any] | None:
    """Fetch retained message payload from EMQX. Returns None if not found or error."""
    try:
        encoded = urllib.parse.quote(topic, safe="")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_api_base(broker)}/retainer/message/{encoded}",
                auth=_auth(broker),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            payload_str = data.get("payload", "")
            if not payload_str:
                return None
            return json.loads(payload_str)
    except Exception:
        return None
