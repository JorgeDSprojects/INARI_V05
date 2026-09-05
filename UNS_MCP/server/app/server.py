"""MCP tool definitions for UNS_SILVER's read-only query surface.

Transport-agnostic: this module is what `mcp run app/server.py` targets
for stdio, and what app/http_main.py imports to serve over HTTP. It knows
nothing about which transport is in use.

See docs/superpowers/specs/2026-09-05-uns-mcp-design.md, Section 2.
"""
from __future__ import annotations

from datetime import datetime

import psycopg
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app import db
from app.config import load_settings

mcp = MCPServer("UNS Silver Query")

_settings = load_settings()


def _connect() -> psycopg.Connection:
    # One connection per tool call, closed immediately after -- simplest
    # correct thing for v1. A connection pool would cut per-call latency
    # under real multi-agent HTTP load; deferred until that's measured to
    # matter, not built speculatively here.
    # connect_timeout keeps an unreachable database a fast, clear error
    # instead of a tool call that hangs for the OS TCP timeout.
    return psycopg.connect(_settings.silver_database_url, autocommit=True, connect_timeout=5)


@mcp.tool()
def get_current_value(topic: str, signal_key: str) -> dict:
    """Get the most recent value of one signal (raw sensor reading or KPI),
    enriched with its unit when known. Raises if the topic/signal_key pair
    has no recorded value -- use list_signals first if unsure of the exact
    signal_key."""
    conn = _connect()
    try:
        return db.get_current_value(conn, topic, signal_key)
    except db.NotFound as exc:
        raise ToolError(str(exc)) from exc
    finally:
        conn.close()


@mcp.tool()
def get_historical_trend(topic: str, signal_key: str, from_time: datetime, to_time: datetime) -> dict:
    """Get a time series for one signal between two timestamps. Automatically
    downsamples for wide ranges (returns pre-aggregated minute/hour buckets
    instead of every raw reading) so the result stays a manageable size
    regardless of the requested range. The result is capped at 1000 points;
    `truncated: true` means there was more data in the range than was
    returned -- narrow the range for full coverage. Raises if the
    topic/signal_key pair is unknown to the system; an empty `points` list
    means the signal exists but has no data in the requested window."""
    conn = _connect()
    try:
        return db.get_historical_trend(conn, topic, signal_key, from_time, to_time)
    except db.NotFound as exc:
        raise ToolError(str(exc)) from exc
    finally:
        conn.close()


@mcp.tool()
def list_signals(topic_prefix: str) -> list[dict]:
    """List every currently-defined signal (raw or KPI) whose topic starts
    with the given prefix, with its unit and description when known. Use
    this to discover what can be asked about under an asset/line/site
    before calling the other tools.

    Coverage depends on `_descriptive` messages having been published for a
    topic: a signal with real data but no catalog entry yet won't appear
    here. get_current_value/get_historical_trend can still be called
    directly if you know the exact signal_key from another source, so an
    empty or thin result here does not mean there is no data."""
    conn = _connect()
    try:
        return db.list_signals(conn, topic_prefix)
    finally:
        conn.close()


@mcp.tool()
def list_active_alarms(topic: str) -> list[dict]:
    """List alarms currently active for the given topic, as of the most
    recent analytical publish for that topic. Returns an empty list if
    there are none (not an error)."""
    conn = _connect()
    try:
        return db.list_active_alarms(conn, topic)
    finally:
        conn.close()
