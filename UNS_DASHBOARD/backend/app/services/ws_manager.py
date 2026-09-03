"""Pure subscription bookkeeping (TopicHub) plus the WebSocket/Redis async
glue that uses it. TopicHub has no I/O and is fully unit tested; the reader
loop is verified manually (see design spec, testing philosophy)."""
from __future__ import annotations

from collections import defaultdict


class TopicHub:
    def __init__(self) -> None:
        self._topic_to_clients: dict[str, set[str]] = defaultdict(set)
        self._client_to_topics: dict[str, set[str]] = defaultdict(set)

    def subscribe(self, client_id: str, topic: str) -> None:
        self._topic_to_clients[topic].add(client_id)
        self._client_to_topics[client_id].add(topic)

    def unsubscribe_all(self, client_id: str) -> None:
        for topic in self._client_to_topics.pop(client_id, set()):
            clients = self._topic_to_clients.get(topic)
            if clients:
                clients.discard(client_id)
                if not clients:
                    del self._topic_to_clients[topic]

    def subscribers_for(self, topic: str) -> set[str]:
        return set(self._topic_to_clients.get(topic, set()))

    def topics(self) -> set[str]:
        return set(self._topic_to_clients.keys())


import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger("uns_dashboard.ws_manager")

hub = TopicHub()
_connections: dict[str, WebSocket] = {}
_reader_tasks: dict[str, asyncio.Task] = {}


async def register(client_id: str, websocket: WebSocket) -> None:
    _connections[client_id] = websocket


async def unregister(client_id: str) -> None:
    hub.unsubscribe_all(client_id)
    _connections.pop(client_id, None)
    for topic in list(_reader_tasks):
        if not hub.subscribers_for(topic):
            _reader_tasks.pop(topic).cancel()


def _stream_key(topic: str) -> str:
    return f"live:{topic}"


async def _read_topic_forever(topic: str) -> None:
    redis_client = aioredis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
    last_id = "$"
    try:
        while hub.subscribers_for(topic):
            response = await redis_client.xread({_stream_key(topic): last_id}, block=5000, count=10)
            for _stream, entries in response or []:
                for entry_id, fields in entries:
                    last_id = entry_id
                    frame = {"topic": topic, "time": fields.get("time"), "payload": json.loads(fields.get("payload", "{}"))}
                    for client_id in hub.subscribers_for(topic):
                        ws = _connections.get(client_id)
                        if ws is not None:
                            try:
                                await ws.send_json(frame)
                            except Exception:
                                logger.warning("Failed to send frame to client %s", client_id)
    finally:
        await redis_client.aclose()


def ensure_reader(topic: str) -> None:
    if topic not in _reader_tasks or _reader_tasks[topic].done():
        _reader_tasks[topic] = asyncio.create_task(_read_topic_forever(topic))
