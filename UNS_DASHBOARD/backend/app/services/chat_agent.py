# UNS_DASHBOARD/backend/app/services/chat_agent.py
"""The provider-agnostic tool-calling loop: reads go through UNS_MCP as
an MCP client, writes execute in-process against this app's own CRUD
services. See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 4.
"""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Chart, Dashboard
from app.services import chart_service, dashboard_service, mcp_client
from app.services.llm_providers.base import LLMProvider

_MAX_ITERATIONS = 8

_WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_dashboard",
            "description": "Create a new draft dashboard. Always do this before adding charts if none exists yet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_chart",
            "description": "Add a chart to an existing draft dashboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "string"},
                    "name": {"type": "string"},
                    "chart_type": {"type": "string", "enum": ["timeseries", "gauge", "kpi", "bar", "table", "status"]},
                    "data_mode": {"type": "string", "enum": ["live", "historical"]},
                    "signals": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string"},
                                "signal_key": {"type": "string"},
                                "label": {"type": "string"},
                                "unit": {"type": "string"},
                            },
                            "required": ["topic", "signal_key"],
                        },
                    },
                },
                "required": ["dashboard_id", "name", "chart_type", "data_mode", "signals"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_chart",
            "description": "Update fields of an existing chart (e.g. its name or color).",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {"type": "string"},
                    "name": {"type": "string"},
                    "color": {"type": "string"},
                },
                "required": ["chart_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_chart",
            "description": "Remove a chart from a dashboard.",
            "parameters": {
                "type": "object",
                "properties": {"chart_id": {"type": "string"}},
                "required": ["chart_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publish_dashboard",
            "description": "Publish a draft dashboard, making it a read-only view. Only do this when the user explicitly asks to publish.",
            "parameters": {
                "type": "object",
                "properties": {"dashboard_id": {"type": "string"}},
                "required": ["dashboard_id"],
            },
        },
    },
]

_WRITE_TOOL_NAMES = {t["function"]["name"] for t in _WRITE_TOOLS}

# The primary key each write tool already consumes separately (as the target
# id, e.g. `db.get(Dashboard, args["dashboard_id"])`) before any remaining
# arguments are forwarded to chart_service/dashboard_service. Used by
# _allowed_write_args to keep that primary key out of the forwarded dict --
# most importantly, update_chart's schema never declares "dashboard_id" in
# the first place, so it can never reach chart_service.update_chart's
# unfiltered setattr via this path. See _dispatch_write_tool.
_PRIMARY_KEY_BY_TOOL = {
    "add_chart": "dashboard_id",
    "update_chart": "chart_id",
    "delete_chart": "chart_id",
    "publish_dashboard": "dashboard_id",
}

_SYSTEM_PROMPT = (
    "You are a helpful assistant that builds SCADA dashboards for an industrial monitoring system. "
    "Use list_signals to discover what signals exist before referencing one -- never guess a signal_key. "
    "IMPORTANT: list_signals' `topic_prefix` argument filters by MQTT TOPIC PATH -- the asset hierarchy, "
    "like 'site/line/machine' -- and NOT by signal name. Never pass a signal name, a signal_key, or a "
    "description as topic_prefix. To find a signal by name, call list_signals with the broadest topic "
    "prefix you actually know (an empty string \"\" lists everything), then search the returned "
    "signal_key/description fields yourself. An empty list_signals result only means nothing matched "
    "THAT TOPIC PATH -- it never proves a named signal does not exist, so never tell the user a signal "
    "is missing on the strength of one narrow list_signals call. "
    "CRITICAL: if your FIRST list_signals call (with any specific topic_prefix guess) returns an empty "
    "result, you MUST immediately call list_signals again with topic_prefix=\"\" in the SAME turn before "
    "saying anything to the user -- do not try a second or third narrow guess, and do not conclude a "
    "signal is missing after only narrow attempts. Only after a topic_prefix=\"\" call also fails to "
    "surface anything plausible should you tell the user you couldn't find it. "
    "Use get_current_value or get_historical_trend to check real data when useful. "
    "Use the write tools to create and edit the dashboard the user is describing. "
    "Always create a dashboard before adding charts to it if the conversation has not created one yet. "
    "Never call publish_dashboard unless the user explicitly asks to publish. "
    "Never claim you have created or modified anything unless a tool call actually returned a result -- "
    "if you intend to call a tool, emit a real tool call, never a description of one in your reply text. "
    "If the request is ambiguous, ask a clarifying question in plain text instead of guessing."
)


async def _build_system_prompt(db: AsyncSession, current_dashboard_id: str | None) -> str:
    prompt = _SYSTEM_PROMPT
    if current_dashboard_id:
        dashboard = await db.get(Dashboard, current_dashboard_id)
        if dashboard is not None:
            prompt += (
                f" The user is currently editing dashboard '{dashboard.name}' (id: {dashboard.id}, "
                f"status: {dashboard.status}). Prefer adding, updating, or deleting charts on THIS "
                "dashboard using add_chart/update_chart/delete_chart -- do NOT call create_dashboard "
                "unless the user clearly asks you to create a separate, additional dashboard."
            )
    return prompt


async def run_turn(
    db: AsyncSession,
    provider: LLMProvider,
    history: list[dict],
    user_message: str,
    read_tools: list[dict] | None = None,
    current_dashboard_id: str | None = None,
) -> tuple[str, list[dict], str | None, list[str]]:
    if read_tools is None:
        read_tools = await mcp_client.list_read_tools()
    tools = _WRITE_TOOLS + read_tools

    messages = list(history)
    if not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": await _build_system_prompt(db, current_dashboard_id)}] + messages

    user_turn = {"role": "user", "content": user_message}
    messages.append(user_turn)
    new_messages: list[dict] = [user_turn]

    dashboard_id: str | None = current_dashboard_id
    actions: list[str] = []
    created_dashboards_this_turn: dict[str, dict] = {}

    for _ in range(_MAX_ITERATIONS):
        response = await provider.send(messages, tools)

        if response.is_final:
            assistant_message = {"role": "assistant", "content": response.text or ""}
            messages.append(assistant_message)
            new_messages.append(assistant_message)
            return response.text or "", new_messages, dashboard_id, actions

        assistant_message = {
            "role": "assistant",
            "content": response.text,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in response.tool_calls
            ],
        }
        messages.append(assistant_message)
        new_messages.append(assistant_message)

        for tc in response.tool_calls:
            try:
                if tc.name in _WRITE_TOOL_NAMES:
                    result = await _dispatch_write_tool(db, tc.name, tc.arguments, created_dashboards_this_turn)
                    if tc.name == "create_dashboard":
                        dashboard_id = result["id"]
                    args_repr = ", ".join(f"{k}={v!r}" for k, v in tc.arguments.items())
                    actions.append(f"{tc.name}({args_repr})")
                else:
                    result = await mcp_client.call_read_tool(tc.name, tc.arguments)
            except Exception as exc:  # noqa: BLE001 -- fed back to the model as a tool error, never raised to the caller
                result = {"error": str(exc)}

            tool_message = {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            }
            messages.append(tool_message)
            new_messages.append(tool_message)

    timeout_reply = "No pude completar la solicitud en el número de pasos permitido. ¿Puedes reformularla de forma más sencilla?"
    new_messages.append({"role": "assistant", "content": timeout_reply})
    return timeout_reply, new_messages, dashboard_id, actions


def _allowed_write_args(tool_name: str) -> dict:
    """Whitelists an LLM tool call's arguments against that tool's own
    declared JSON-schema `properties` (from _WRITE_TOOLS), minus whichever
    key is already consumed separately as the primary target id.

    This exists because chart_service.create_chart/update_chart do an
    unfiltered Chart(**data)/setattr over whatever dict they're handed --
    correct for the REST routers (which filter through a Pydantic model
    first) but NOT safe to expose directly to an LLM's tool-call arguments,
    which are attacker-influenced input. Without this, a crafted
    update_chart call carrying an extra "dashboard_id" would move a chart
    into an already-published dashboard, bypassing the draft-only guard
    (which only checks the chart's CURRENT dashboard, not the target of the
    move). Deriving the whitelist from the tool schema itself (rather than
    hardcoding a list per tool) keeps it from silently drifting out of sync
    if a tool's schema changes.
    """
    schema = next(t["function"]["parameters"] for t in _WRITE_TOOLS if t["function"]["name"] == tool_name)
    allowed = set(schema.get("properties", {}))
    allowed.discard(_PRIMARY_KEY_BY_TOOL.get(tool_name))
    return allowed


def _filter_write_args(tool_name: str, args: dict) -> dict:
    allowed = _allowed_write_args(tool_name)
    return {k: v for k, v in args.items() if k in allowed}


async def _dispatch_write_tool(
    db: AsyncSession, name: str, args: dict, created_dashboards_this_turn: dict[str, dict]
) -> dict:
    # The chat only ever edits DRAFT dashboards (never a published one) --
    # this cannot live in dashboard_service/chart_service (Task 5), since
    # those are shared with the existing REST API, which has no such
    # restriction today and must keep behaving exactly as it does now.
    if name == "create_dashboard":
        # A model can (and, in a real observed conversation, did) emit a
        # second create_dashboard call with the SAME name within one turn --
        # e.g. after already seeing the first call's result on a later loop
        # iteration, it re-emits the create instead of only add_chart. Without
        # this guard that produces a second, empty, duplicate dashboard while
        # the correctly-configured charts stay attached to the first (now
        # orphaned) one. Keyed by name only (this turn's scope), so a
        # legitimate second dashboard with a different name is unaffected.
        existing = created_dashboards_this_turn.get(args["name"])
        if existing is not None:
            return existing
        dashboard = await dashboard_service.create_dashboard(db, args["name"], args.get("description"))
        result = {"id": dashboard.id, "name": dashboard.name}
        created_dashboards_this_turn[args["name"]] = result
        return result
    if name == "add_chart":
        await _ensure_dashboard_is_draft(db, args["dashboard_id"])
        chart = await chart_service.create_chart(db, args["dashboard_id"], _filter_write_args("add_chart", args))
        return {"id": chart.id, "name": chart.name}
    if name == "update_chart":
        await _ensure_chart_dashboard_is_draft(db, args["chart_id"])
        chart = await chart_service.update_chart(db, args["chart_id"], _filter_write_args("update_chart", args))
        return {"id": chart.id}
    if name == "delete_chart":
        await _ensure_chart_dashboard_is_draft(db, args["chart_id"])
        await chart_service.delete_chart(db, args["chart_id"])
        return {"deleted": args["chart_id"]}
    if name == "publish_dashboard":
        await _ensure_dashboard_is_draft(db, args["dashboard_id"])
        dashboard = await dashboard_service.publish_dashboard(db, args["dashboard_id"])
        return {"id": dashboard.id, "status": dashboard.status}
    raise ValueError(f"Unknown write tool: {name}")


async def _ensure_dashboard_is_draft(db: AsyncSession, dashboard_id: str) -> None:
    dashboard = await db.get(Dashboard, dashboard_id)
    if dashboard is None:
        raise ValueError(f"Dashboard not found: {dashboard_id}")
    if dashboard.status != "draft":
        raise ValueError("This dashboard is already published; the chat can only edit drafts.")


async def _ensure_chart_dashboard_is_draft(db: AsyncSession, chart_id: str) -> None:
    chart = await db.get(Chart, chart_id)
    if chart is None:
        raise ValueError(f"Chart not found: {chart_id}")
    await _ensure_dashboard_is_draft(db, chart.dashboard_id)
