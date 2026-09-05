import os

import pytest
import pytest_asyncio

from app.database import AsyncSessionLocal, create_tables
from app.services import chat_agent
from app.services.llm_providers.base import ProviderResponse, ToolCall

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; requires a live Postgres (docker compose up -d dashboard_postgres)"
)


class _ScriptedProvider:
    """Replays a fixed sequence of responses, one per call to send()."""

    def __init__(self, responses: list[ProviderResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[list[dict], list[dict]]] = []

    async def send(self, messages, tools):
        self.calls.append((messages, tools))
        return self._responses.pop(0)


@pytest_asyncio.fixture
async def db():
    await create_tables()
    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_final_text_reply_with_no_tool_calls(db):
    provider = _ScriptedProvider([ProviderResponse(text="Hola, ¿qué quieres crear?", tool_calls=[])])

    reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(db, provider, [], "hola", read_tools=[])

    assert reply == "Hola, ¿qué quieres crear?"
    assert dashboard_id is None
    assert actions == []
    assert new_messages[0] == {"role": "user", "content": "hola"}


@pytest.mark.asyncio
async def test_create_dashboard_tool_call_binds_dashboard_id(db):
    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="1", name="create_dashboard", arguments={"name": "pytest-chat-dash"})]),
        ProviderResponse(text="Listo, he creado el dashboard.", tool_calls=[]),
    ])

    reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(
        db, provider, [], "crea un dashboard llamado pytest-chat-dash", read_tools=[]
    )

    assert dashboard_id is not None
    assert "create_dashboard" in actions[0]
    assert reply == "Listo, he creado el dashboard."


@pytest.mark.asyncio
async def test_unknown_write_tool_result_fed_back_as_tool_error_not_raised(db):
    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="1", name="publish_dashboard", arguments={"dashboard_id": "does-not-exist"})]),
        ProviderResponse(text="No encontré ese dashboard.", tool_calls=[]),
    ])

    reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(db, provider, [], "publica ese dashboard", read_tools=[])

    assert reply == "No encontré ese dashboard."
    tool_result_messages = [m for m in new_messages if m.get("role") == "tool"]
    assert len(tool_result_messages) == 1
    assert "error" in tool_result_messages[0]["content"].lower() or "not found" in tool_result_messages[0]["content"].lower()


@pytest.mark.asyncio
async def test_loop_is_bounded_and_returns_a_graceful_message(db):
    # 8 tool-call responses in a row, never a final text reply -- must not loop forever.
    responses = [
        ProviderResponse(text=None, tool_calls=[ToolCall(id=str(i), name="list_signals", arguments={"topic_prefix": ""})])
        for i in range(8)
    ]
    provider = _ScriptedProvider(responses)

    reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(db, provider, [], "haz algo ambiguo", read_tools=[])

    assert "no pude completar" in reply.lower()
    assert len(provider.calls) == 8


@pytest.mark.asyncio
async def test_write_tools_refuse_to_touch_a_published_dashboard(db):
    from app.services import dashboard_service

    dashboard = await dashboard_service.create_dashboard(db, "pytest-published-dashboard")
    await dashboard_service.publish_dashboard(db, dashboard.id)

    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(
            id="1", name="add_chart",
            arguments={"dashboard_id": dashboard.id, "name": "x", "chart_type": "kpi", "data_mode": "live", "signals": []},
        )]),
        ProviderResponse(text="Ese dashboard ya está publicado, no puedo editarlo desde el chat.", tool_calls=[]),
    ])

    reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(
        db, provider, [], "añade una gráfica a ese dashboard publicado", read_tools=[]
    )

    assert actions == []  # the tool call was rejected before it could count as a completed action
    tool_result_messages = [m for m in new_messages if m.get("role") == "tool"]
    assert "draft" in tool_result_messages[0]["content"].lower() or "publicado" in reply.lower() or "already published" in tool_result_messages[0]["content"].lower()


@pytest.mark.asyncio
async def test_system_prompt_is_prepended_only_once(db):
    provider = _ScriptedProvider([ProviderResponse(text="ok", tool_calls=[])])
    existing_history = [{"role": "user", "content": "mensaje anterior"}, {"role": "assistant", "content": "respuesta anterior"}]

    await chat_agent.run_turn(db, provider, existing_history, "otro mensaje", read_tools=[])

    sent_messages = provider.calls[0][0]
    system_messages = [m for m in sent_messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    assert system_messages[0] == sent_messages[0]
