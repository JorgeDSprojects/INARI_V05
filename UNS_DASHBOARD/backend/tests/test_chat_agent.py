import json
import os

import pytest
import pytest_asyncio
from sqlalchemy.future import select

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

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(db, provider, [], "hola", read_tools=[])

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

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(
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

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(db, provider, [], "publica ese dashboard", read_tools=[])

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

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(db, provider, [], "haz algo ambiguo", read_tools=[])

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

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(
        db, provider, [], "añade una gráfica a ese dashboard publicado", read_tools=[]
    )

    assert actions == []  # the tool call was rejected before it could count as a completed action
    tool_result_messages = [m for m in new_messages if m.get("role") == "tool"]
    assert "draft" in tool_result_messages[0]["content"].lower() or "publicado" in reply.lower() or "already published" in tool_result_messages[0]["content"].lower()


@pytest.mark.asyncio
async def test_update_chart_cannot_move_a_chart_into_a_published_dashboard_via_dashboard_id(db):
    """Reproduces the mass-assignment attack found by the final review: a
    crafted update_chart call carrying an extra "dashboard_id" argument must
    NOT be able to move a chart out of its current draft dashboard into an
    already-published one. _dispatch_write_tool must whitelist update_chart's
    forwarded arguments against its own declared schema (name, color only)
    rather than forwarding the LLM's raw argument dict straight into
    chart_service.update_chart's unfiltered setattr.
    """
    from app.models.dashboard import Chart
    from app.services import dashboard_service

    draft_dashboard = await dashboard_service.create_dashboard(db, "pytest-attack-draft-dashboard")
    published_dashboard = await dashboard_service.create_dashboard(db, "pytest-attack-published-dashboard")
    await dashboard_service.publish_dashboard(db, published_dashboard.id)

    create_provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(
            id="1", name="add_chart",
            arguments={
                "dashboard_id": draft_dashboard.id, "name": "victim-chart",
                "chart_type": "kpi", "data_mode": "live", "signals": [],
            },
        )]),
        ProviderResponse(text="Listo.", tool_calls=[]),
    ])
    _, _, _, actions, _ = await chat_agent.run_turn(
        db, create_provider, [], "añade una gráfica al dashboard borrador", read_tools=[]
    )
    assert actions  # add_chart succeeded

    result = await db.execute(select(Chart).where(Chart.dashboard_id == draft_dashboard.id))
    chart = result.scalar_one()

    attack_provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(
            id="1", name="update_chart",
            arguments={"chart_id": chart.id, "name": "renamed", "dashboard_id": published_dashboard.id},
        )]),
        ProviderResponse(text="Listo, actualizado.", tool_calls=[]),
    ])
    await chat_agent.run_turn(db, attack_provider, [], "actualiza esa gráfica", read_tools=[])

    await db.refresh(chart)
    assert chart.dashboard_id == draft_dashboard.id  # NOT moved into the published dashboard
    assert chart.name == "renamed"  # the whitelisted field still applied normally


@pytest.mark.asyncio
async def test_system_prompt_mentions_the_currently_edited_dashboard(db):
    from app.services import dashboard_service

    dashboard = await dashboard_service.create_dashboard(db, "pytest-current-dashboard")

    provider = _ScriptedProvider([ProviderResponse(text="ok", tool_calls=[])])
    await chat_agent.run_turn(db, provider, [], "hola", read_tools=[], current_dashboard_id=dashboard.id)

    system_message = provider.calls[0][0][0]
    assert system_message["role"] == "system"
    assert dashboard.name in system_message["content"]


@pytest.mark.asyncio
async def test_add_chart_against_current_dashboard_id_does_not_require_create_dashboard(db):
    from app.services import dashboard_service

    dashboard = await dashboard_service.create_dashboard(db, "pytest-current-dashboard-add-chart")

    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(
            id="1", name="add_chart",
            arguments={
                "dashboard_id": dashboard.id, "name": "rpm gauge",
                "chart_type": "gauge", "data_mode": "live", "signals": [],
            },
        )]),
        ProviderResponse(text="Listo, he añadido la gráfica.", tool_calls=[]),
    ])

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(
        db, provider, [], "añade un gauge de RPM", read_tools=[], current_dashboard_id=dashboard.id
    )

    assert dashboard_id == dashboard.id  # reflects the pre-existing id, not None
    assert any("add_chart" in a for a in actions)
    assert not any("create_dashboard" in a for a in actions)


@pytest.mark.asyncio
async def test_duplicate_create_dashboard_calls_in_one_turn_are_idempotent(db):
    from app.models.dashboard import Dashboard

    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[
            ToolCall(id="1", name="create_dashboard", arguments={"name": "pytest-dup-dashboard"}),
            ToolCall(id="2", name="create_dashboard", arguments={"name": "pytest-dup-dashboard"}),
        ]),
        ProviderResponse(text="Listo, he creado el dashboard.", tool_calls=[]),
    ])

    reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(
        db, provider, [], "crea un dashboard llamado pytest-dup-dashboard", read_tools=[]
    )

    result = await db.execute(select(Dashboard).where(Dashboard.name == "pytest-dup-dashboard"))
    dashboards = result.scalars().all()
    assert len(dashboards) == 1  # only one dashboard actually created

    tool_result_messages = [m for m in new_messages if m.get("role") == "tool"]
    assert len(tool_result_messages) == 2
    first_id = json.loads(tool_result_messages[0]["content"])["id"]
    second_id = json.loads(tool_result_messages[1]["content"])["id"]
    assert first_id == second_id == dashboards[0].id


@pytest.mark.asyncio
async def test_system_prompt_is_prepended_only_once(db):
    provider = _ScriptedProvider([ProviderResponse(text="ok", tool_calls=[])])
    existing_history = [{"role": "user", "content": "mensaje anterior"}, {"role": "assistant", "content": "respuesta anterior"}]

    await chat_agent.run_turn(db, provider, existing_history, "otro mensaje", read_tools=[])

    sent_messages = provider.calls[0][0]
    system_messages = [m for m in sent_messages if m.get("role") == "system"]
    assert len(system_messages) == 1
    assert system_messages[0] == sent_messages[0]


@pytest.mark.asyncio
async def test_present_signal_candidates_ends_the_turn_with_candidates_populated(db):
    candidates = [
        {"topic": "GALERNA/T01/GENERATOR", "signal_key": "Gen_RPM_Max", "signal_type": "kpi", "unit": "rpm", "description": "Peak RPM"},
        {"topic": "GALERNA/T01/GENERATOR/_informative", "signal_key": "Gen_RPM_Max_Raw", "signal_type": "raw", "unit": "rpm", "description": None},
    ]
    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="1", name="present_signal_candidates", arguments={"candidates": candidates})]),
    ])

    reply, new_messages, dashboard_id, actions, returned_candidates = await chat_agent.run_turn(
        db, provider, [], "busca el rpm del generador", read_tools=[]
    )

    assert returned_candidates == candidates
    assert actions == []  # presenting candidates is not a write action
    assert len(provider.calls) == 1  # the turn ended immediately, no further loop iteration
    tool_result_messages = [m for m in new_messages if m.get("role") == "tool"]
    assert len(tool_result_messages) == 1


@pytest.mark.asyncio
async def test_present_signal_candidates_with_empty_list_is_rejected_as_a_tool_error(db):
    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="1", name="present_signal_candidates", arguments={"candidates": []})]),
        ProviderResponse(text="Perdona, no encontré nada. ¿Puedes darme más detalles?", tool_calls=[]),
    ])

    reply, new_messages, dashboard_id, actions, returned_candidates = await chat_agent.run_turn(
        db, provider, [], "busca algo", read_tools=[]
    )

    assert returned_candidates is None  # rejected, never surfaced to the user
    assert len(provider.calls) == 2  # the loop continued after the rejection
    tool_result_messages = [m for m in new_messages if m.get("role") == "tool"]
    assert "empty" in tool_result_messages[0]["content"].lower() or "error" in tool_result_messages[0]["content"].lower()


@pytest.mark.asyncio
async def test_present_signal_candidates_is_truncated_to_a_maximum_of_8(db):
    many_candidates = [
        {"topic": f"GALERNA/T0{i}/GENERATOR", "signal_key": f"Gen_RPM_{i}", "signal_type": "kpi", "unit": "rpm", "description": None}
        for i in range(12)
    ]
    provider = _ScriptedProvider([
        ProviderResponse(text=None, tool_calls=[ToolCall(id="1", name="present_signal_candidates", arguments={"candidates": many_candidates})]),
    ])

    _, _, _, _, returned_candidates = await chat_agent.run_turn(db, provider, [], "busca algo", read_tools=[])

    assert len(returned_candidates) == 8


@pytest.mark.asyncio
async def test_normal_write_tool_turn_returns_none_candidates(db):
    provider = _ScriptedProvider([ProviderResponse(text="Hola", tool_calls=[])])

    _, _, _, _, returned_candidates = await chat_agent.run_turn(db, provider, [], "hola", read_tools=[])

    assert returned_candidates is None
