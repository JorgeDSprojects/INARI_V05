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

_SYSTEM_PROMPT = (
    "You are a helpful assistant that builds SCADA dashboards for an industrial monitoring system. "
    "Use list_signals to discover what signals exist before referencing one -- never guess a signal_key. "
    "Use get_current_value or get_historical_trend to check real data when useful. "
    "Use the write tools to create and edit the dashboard the user is describing. "
    "Always create a dashboard before adding charts to it if the conversation has not created one yet. "
    "Never call publish_dashboard unless the user explicitly asks to publish. "
    "If the request is ambiguous, ask a clarifying question in plain text instead of guessing."
)


async def run_turn(
    db: AsyncSession,
    provider: LLMProvider,
    history: list[dict],
    user_message: str,
    read_tools: list[dict] | None = None,
) -> tuple[str, list[dict], str | None, list[str]]:
    if read_tools is None:
        read_tools = await mcp_client.list_read_tools()
    tools = _WRITE_TOOLS + read_tools

    messages = list(history)
    if not any(m.get("role") == "system" for m in messages):
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + messages

    user_turn = {"role": "user", "content": user_message}
    messages.append(user_turn)
    new_messages: list[dict] = [user_turn]

    dashboard_id: str | None = None
    actions: list[str] = []

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
                    result = await _dispatch_write_tool(db, tc.name, tc.arguments)
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


async def _dispatch_write_tool(db: AsyncSession, name: str, args: dict) -> dict:
    # The chat only ever edits DRAFT dashboards (never a published one) --
    # this cannot live in dashboard_service/chart_service (Task 5), since
    # those are shared with the existing REST API, which has no such
    # restriction today and must keep behaving exactly as it does now.
    if name == "create_dashboard":
        dashboard = await dashboard_service.create_dashboard(db, args["name"], args.get("description"))
        return {"id": dashboard.id, "name": dashboard.name}
    if name == "add_chart":
        await _ensure_dashboard_is_draft(db, args["dashboard_id"])
        chart = await chart_service.create_chart(db, args["dashboard_id"], {k: v for k, v in args.items() if k != "dashboard_id"})
        return {"id": chart.id, "name": chart.name}
    if name == "update_chart":
        await _ensure_chart_dashboard_is_draft(db, args["chart_id"])
        chart = await chart_service.update_chart(db, args["chart_id"], {k: v for k, v in args.items() if k != "chart_id"})
        return {"id": chart.id}
    if name == "delete_chart":
        await _ensure_chart_dashboard_is_draft(db, args["chart_id"])
        await chart_service.delete_chart(db, args["chart_id"])
        return {"deleted": args["chart_id"]}
    if name == "publish_dashboard":
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
