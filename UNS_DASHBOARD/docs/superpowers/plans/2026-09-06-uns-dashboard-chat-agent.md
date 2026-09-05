# UNS Dashboard Chat Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in chat panel to `UNS_DASHBOARD` that creates and edits draft dashboards from natural-language requests, piloted on a local, GPU-accelerated Ollama instance, behind a provider-agnostic abstraction that also accommodates OpenAI, OpenRouter, a remote DGX Spark, and (later) Claude.

**Architecture:** A new `UNS_OLLAMA/` module runs one GPU-accelerated Ollama container on the shared network. `UNS_DASHBOARD/backend` gains a chat subsystem that runs its own provider-agnostic tool-calling loop: it is an MCP *client* of the already-built `UNS_MCP` for the four read tools, and executes five new write tools in-process against `UNS_DASHBOARD`'s own (lightly refactored, behavior-preserved) CRUD code. Conversation history persists per session in two new tables. The existing editor, viewer, and REST API are untouched — the chat is additive.

**Tech Stack:** Python 3.12, FastAPI/SQLAlchemy (existing), `openai` SDK (new — used generically against any OpenAI-compatible endpoint), `mcp` SDK client mode (new), Ollama (`ollama/ollama` image), React/TypeScript (existing frontend).

**Spec:** `UNS_DASHBOARD/docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md`

## Global Constraints

- This is strictly additive. No existing `UNS_DASHBOARD` endpoint, model, or frontend behavior changes except where Task 5 explicitly extracts existing router logic into service functions — and that extraction must not change any existing endpoint's observable behavior (status codes, response bodies, error cases). The existing test suites (`test_dashboards_router.py`, `test_charts_router.py`, and every other existing test file) must keep passing unmodified.
- The chat only ever operates on **draft** dashboards. No tool exists for editing a published dashboard, and no tool exists for `delete_dashboard` — deleting an entire dashboard requires the existing UI.
- Two adapter *types*, not one per provider: `openai_compatible` (real `openai` SDK pointed at any OpenAI-compatible `base_url` — covers Ollama, a future DGX Spark, OpenAI, OpenRouter) and `anthropic` (interface only this milestone, no implementation).
- If no provider is configured (`LLM_PROVIDER_TYPE` unset/`none`) or the configured self-hosted provider doesn't respond, the chat must not silently pretend to work: `GET /chat/status` reports `available: false` with a reason, the frontend disables the message input, and mid-conversation provider failures return HTTP 503.
- `UNS_DASHBOARD/backend` reaches `UNS_SILVER`'s data **only** through `UNS_MCP` as an MCP client (never a direct Postgres connection to Silver) — the read tools are exactly `UNS_MCP`'s four tools, never duplicated or reimplemented.
- The MCP SDK API used in this plan was verified live during planning against `py.sdk.modelcontextprotocol.io` for `mcp==2.1.1` (`from mcp import Client`, `client.list_tools()`, `client.call_tool(name, args)`, `result.structured_content`/`result.is_error`) — but the exact package needed to attach a custom HTTP header (`X-MCP-API-Key`) to the client's transport was NOT reliably confirmed (one fetch mentioned a package called `httpx2`, which does not match this project's existing `httpx` dependency and may be a research artifact, not a real package). Task 4 has an explicit verification step for this — do not guess; confirm against the actually-installed `mcp` package.
- Ollama's OpenAI-compatible endpoint (`/v1/chat/completions`, supporting the `tools` parameter, non-streaming) was verified live during planning — the `openai` Python SDK works against it unmodified via `AsyncOpenAI(base_url=..., api_key=...)`.
- All code, comments, and commit messages in English (per repo `AGENTS.md`). `UNS_OLLAMA/` gets the required `scripts/{up,down,restart,logs,status}.sh` per `AGENTS.md`.
- This project has no migration tool (confirmed: neither `UNS_MANAGER`'s nor `UNS_DASHBOARD`'s backend uses Alembic) — new tables are added the same way `dashboards`/`charts` already are: a new SQLAlchemy model file, imported into `app/database.py`'s `create_tables()`, which runs `Base.metadata.create_all` at app startup.
- Service keys/ports: `UNS_OLLAMA`'s compose service is named `ollama` (container `uns_ollama`) — no collision risk since no other stack defines that key. Host port `11434` (Ollama's own default) unless already in use on the target machine, in which case pick the next free port and note it.

---

## Task 1: `UNS_OLLAMA` — GPU-accelerated Ollama container

**Files:**
- Create: `UNS_OLLAMA/docker-compose.yml`
- Create: `UNS_OLLAMA/.env.example`
- Create: `UNS_OLLAMA/.gitignore`
- Create: `UNS_OLLAMA/scripts/up.sh`, `down.sh`, `restart.sh`, `logs.sh`, `status.sh`
- Create: `UNS_OLLAMA/README.md`

**Interfaces:**
- Produces: a running `ollama` service reachable at `http://uns_ollama:11434` from the shared network, with the `qwen2.5:14b-instruct` model pulled and GPU-accelerated.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: uns_ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "${OLLAMA_PORT:-11434}:11434"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    networks:
      - uns_manager_net
    restart: unless-stopped

volumes:
  ollama_data:
    name: uns_ollama_ollama_data

networks:
  uns_manager_net:
    external: true
    name: ${UNS_MANAGER_NETWORK_NAME:-uns_manager_uns_net}
```

- [ ] **Step 2: Write `.env.example`**

```
OLLAMA_PORT=11434
OLLAMA_MODEL=qwen2.5:14b-instruct
UNS_MANAGER_NETWORK_NAME=uns_manager_uns_net
```

- [ ] **Step 3: Write `.gitignore`**

```
.env
```

- [ ] **Step 4: Write the operational scripts**

```bash
# UNS_OLLAMA/scripts/up.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d
echo "UNS Ollama is starting. Use scripts/status.sh to check container health, then pull a model:"
echo "  docker exec uns_ollama ollama pull \${OLLAMA_MODEL:-qwen2.5:14b-instruct}"
```

```bash
# UNS_OLLAMA/scripts/down.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
```

```bash
# UNS_OLLAMA/scripts/restart.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose restart
```

```bash
# UNS_OLLAMA/scripts/logs.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose logs -f
```

```bash
# UNS_OLLAMA/scripts/status.sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
```

- [ ] **Step 5: Bring it up, verify GPU access, and pull the pilot model**

```bash
cd UNS_OLLAMA
cp .env.example .env
chmod +x scripts/*.sh
./scripts/up.sh
docker exec uns_ollama nvidia-smi
```
Expected: `nvidia-smi` inside the container lists the RTX 5090 (not an error about missing drivers/devices). If it fails, `nvidia-container-toolkit` is not actually wired up on this host the way it was expected to be — stop and report BLOCKED with the exact error rather than shipping a CPU-only fallback silently; the design assumed working GPU passthrough.

```bash
docker exec uns_ollama ollama pull qwen2.5:14b-instruct
docker exec uns_ollama ollama run qwen2.5:14b-instruct "Say OK if you can hear me." --verbose
```
Expected: the model responds, and `--verbose` output shows GPU-backed inference (check for a `total duration`/eval-rate line consistent with GPU speed, not CPU-only speed — a 14B model on CPU is dramatically slower per-token than on a 5090; note both numbers in your report).

- [ ] **Step 6: Verify tool-calling works against the OpenAI-compatible endpoint**

```bash
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:14b-instruct",
    "messages": [{"role": "user", "content": "What is the weather in Madrid?"}],
    "tools": [{"type": "function", "function": {"name": "get_weather", "description": "Get the weather for a city", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
  }'
```
Expected: the response's `choices[0].message.tool_calls` contains a call to `get_weather` with `arguments` a JSON string like `"{\"city\": \"Madrid\"}"`. This is the exact mechanism Task 3 depends on — if it doesn't produce a tool call here, stop and report BLOCKED (a different/larger model may be needed, or the endpoint may need `tool_choice` set — investigate and report findings rather than silently picking a different model).

- [ ] **Step 7: Write the README**

```markdown
# UNS Ollama

A GPU-accelerated local LLM host for `UNS_DASHBOARD`'s chat agent (and any
future consumer). Not a dependency of any other module — purely an
inference backend reached over HTTP.

See `UNS_DASHBOARD/docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md`
for how this fits into the broader system.

## Quickstart

```bash
cp .env.example .env
./scripts/up.sh
docker exec uns_ollama ollama pull qwen2.5:14b-instruct
```

## Pointing at a remote inference host instead (e.g. a DGX Spark)

This container is optional. `UNS_DASHBOARD/backend`'s `LLM_BASE_URL` can
point at any OpenAI-compatible endpoint instead — including Ollama or
vLLM running on a remote machine — with no code change, only
configuration. Set `LLM_BASE_URL` to that machine's address and stop
(or never start) this local container.

## Operations

- `./scripts/up.sh` / `down.sh` / `restart.sh` / `logs.sh` / `status.sh`
```

- [ ] **Step 8: Commit**

```bash
cd UNS_OLLAMA
git add docker-compose.yml .env.example .gitignore scripts/ README.md
git commit -m "feat(uns-ollama): add GPU-accelerated Ollama container"
```

---

## Task 2: Chat data model (`UNS_DASHBOARD/backend`)

**Files:**
- Create: `UNS_DASHBOARD/backend/app/models/chat.py`
- Create: `UNS_DASHBOARD/backend/app/schemas/chat.py`
- Modify: `UNS_DASHBOARD/backend/app/database.py`
- Create: `UNS_DASHBOARD/backend/tests/test_chat_models.py`

**Interfaces:**
- Produces: `ChatSession` and `ChatMessage` SQLAlchemy models; `ChatStatus`, `ChatSessionCreated`, `ChatMessageRequest`, `ChatMessageResponse`, `ChatMessageRead`, `ChatSessionRead` Pydantic schemas.

- [ ] **Step 1: Write the models**

```python
# UNS_DASHBOARD/backend/app/models/chat.py
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dashboard_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("dashboards.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")
```

- [ ] **Step 2: Write the schemas**

```python
# UNS_DASHBOARD/backend/app/schemas/chat.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatStatus(BaseModel):
    available: bool
    provider_type: str | None
    reason: str | None


class ChatSessionCreated(BaseModel):
    id: str


class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    reply: str
    dashboard_id: str | None
    actions: list[str]


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: dict[str, Any]


class ChatSessionRead(BaseModel):
    dashboard_id: str | None
    messages: list[ChatMessageRead]
```

- [ ] **Step 3: Register the new model in `database.py`**

Edit `UNS_DASHBOARD/backend/app/database.py` — change:
```python
async def create_tables() -> None:
    from app.models import dashboard  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```
to:
```python
async def create_tables() -> None:
    from app.models import chat, dashboard  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Write a test proving the tables are created and relate correctly**

```python
# UNS_DASHBOARD/backend/tests/test_chat_models.py
import pytest

from app.database import AsyncSessionLocal, create_tables
from app.models.chat import ChatMessage, ChatSession
from app.models.dashboard import Dashboard


@pytest.mark.asyncio
async def test_chat_session_and_messages_persist_and_relate():
    await create_tables()
    async with AsyncSessionLocal() as db:
        dashboard = Dashboard(name="pytest-chat-model-dashboard")
        db.add(dashboard)
        await db.flush()

        session = ChatSession(dashboard_id=dashboard.id)
        db.add(session)
        await db.flush()

        message = ChatMessage(session_id=session.id, role="user", content={"text": "hola"})
        db.add(message)
        await db.commit()

        await db.refresh(session, attribute_names=["messages"])
        assert len(session.messages) == 1
        assert session.messages[0].content == {"text": "hola"}

        await db.delete(dashboard)
        await db.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `UNS_DASHBOARD/backend/`, against the live `uns_dashboard_postgres`): `pytest tests/test_chat_models.py -v`
Expected: PASS. This also proves `ON DELETE CASCADE` from `dashboards` → `chat_sessions` doesn't error (deleting the dashboard at the end must not raise).

- [ ] **Step 6: Run the full existing test suite to confirm no regression**

Run: `pytest tests/ -v`
Expected: PASS (all existing tests, unaffected by this additive change).

- [ ] **Step 7: Commit**

```bash
cd UNS_DASHBOARD/backend
git add app/models/chat.py app/schemas/chat.py app/database.py tests/test_chat_models.py
git commit -m "feat(uns-dashboard): add chat session/message data model"
```

---

## Task 3: LLM provider abstraction + `openai_compatible` adapter

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/llm_providers/__init__.py`
- Create: `UNS_DASHBOARD/backend/app/services/llm_providers/base.py`
- Create: `UNS_DASHBOARD/backend/app/services/llm_providers/openai_compatible.py`
- Modify: `UNS_DASHBOARD/backend/requirements.txt`
- Create: `UNS_DASHBOARD/backend/tests/test_openai_compatible_provider.py`

**Interfaces:**
- Produces: `ToolCall(id, name, arguments)`, `ProviderResponse(text, tool_calls)` with `.is_final`, `LLMProvider` protocol with `async def send(messages, tools) -> ProviderResponse`; `OpenAICompatibleProvider(base_url, api_key, model, client=None)` implementing it.

- [ ] **Step 1: Add the `openai` package**

Add to `UNS_DASHBOARD/backend/requirements.txt`:
```
openai==1.57.0
```
Run `pip install -r requirements.txt` (or however this backend's environment is managed) and confirm it installs cleanly before proceeding — if `1.57.0` is unavailable, use whatever recent version `pip` resolves and update the pin to match; note this in your report rather than guessing a version that doesn't exist.

- [ ] **Step 2: Write `base.py`**

```python
# UNS_DASHBOARD/backend/app/services/llm_providers/base.py
"""Provider-agnostic shapes for the chat agent's tool-calling loop.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class LLMProvider(Protocol):
    async def send(self, messages: list[dict], tools: list[dict]) -> ProviderResponse: ...
```

- [ ] **Step 3: Write the failing tests**

```python
# UNS_DASHBOARD/backend/tests/test_openai_compatible_provider.py
import json
from types import SimpleNamespace

import pytest

from app.services.llm_providers.openai_compatible import OpenAICompatibleProvider


class _FakeCompletions:
    def __init__(self, response):
        self._response = response

    async def create(self, **kwargs):
        self.last_call = kwargs
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeClient:
    def __init__(self, response):
        self.chat = _FakeChat(response)


def _make_response(content, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_send_returns_final_text_when_no_tool_calls():
    response = _make_response("Hola, ¿en qué puedo ayudarte?", tool_calls=None)
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="m", client=_FakeClient(response))

    result = await provider.send(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert result.is_final
    assert result.text == "Hola, ¿en qué puedo ayudarte?"
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_send_parses_tool_calls_and_decodes_json_arguments():
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="list_signals", arguments=json.dumps({"topic_prefix": "T01"})),
    )
    response = _make_response(None, tool_calls=[tool_call])
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="m", client=_FakeClient(response))

    result = await provider.send(messages=[], tools=[])

    assert not result.is_final
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "list_signals"
    assert result.tool_calls[0].arguments == {"topic_prefix": "T01"}


@pytest.mark.asyncio
async def test_send_passes_model_messages_and_tools_through():
    response = _make_response("ok", tool_calls=None)
    fake_client = _FakeClient(response)
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="qwen2.5:14b-instruct", client=fake_client)

    messages = [{"role": "user", "content": "hola"}]
    tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]
    await provider.send(messages, tools)

    assert fake_client.chat.completions.last_call["model"] == "qwen2.5:14b-instruct"
    assert fake_client.chat.completions.last_call["messages"] == messages
    assert fake_client.chat.completions.last_call["tools"] == tools


@pytest.mark.asyncio
async def test_send_passes_none_for_tools_when_empty():
    response = _make_response("ok", tool_calls=None)
    fake_client = _FakeClient(response)
    provider = OpenAICompatibleProvider(base_url="http://fake", api_key="x", model="m", client=fake_client)

    await provider.send(messages=[], tools=[])

    assert fake_client.chat.completions.last_call["tools"] is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run (from `UNS_DASHBOARD/backend/`): `pytest tests/test_openai_compatible_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.llm_providers.openai_compatible'`

- [ ] **Step 5: Implement `openai_compatible.py`**

```python
# UNS_DASHBOARD/backend/app/services/llm_providers/openai_compatible.py
"""Adapter for any OpenAI-compatible chat-completions endpoint: Ollama
(local or remote), vLLM, OpenAI itself, and OpenRouter all speak this
same wire format -- only base_url/api_key/model differ.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 5.
"""
from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.services.llm_providers.base import ProviderResponse, ToolCall


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str, client: object | None = None):
        self._client = client or AsyncOpenAI(base_url=base_url, api_key=api_key or "unused")
        self._model = model

    async def send(self, messages: list[dict], tools: list[dict]) -> ProviderResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools or None,
        )
        message = response.choices[0].message
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments))
            for tc in (message.tool_calls or [])
        ]
        return ProviderResponse(text=message.content, tool_calls=tool_calls)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_openai_compatible_provider.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt app/services/llm_providers/ tests/test_openai_compatible_provider.py
git commit -m "feat(uns-dashboard): add LLM provider abstraction and openai-compatible adapter"
```

---

## Task 4: MCP client wrapper

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/mcp_client.py`
- Modify: `UNS_DASHBOARD/backend/app/config.py`
- Modify: `UNS_DASHBOARD/backend/requirements.txt`
- Create: `UNS_DASHBOARD/backend/tests/test_mcp_client.py`

**Interfaces:**
- Produces: `async def list_read_tools() -> list[dict]` (OpenAI function-tool shape, one per `UNS_MCP` tool), `async def call_read_tool(name: str, arguments: dict) -> Any`.

- [ ] **Step 1: Verify the exact way to attach a custom header to the MCP client's transport**

This is flagged as unverified in the Global Constraints — resolve it for real before writing the implementation:
```bash
python -c "import mcp.client.streamable_http as m; help(m.streamable_http_client)"
```
Confirm: (a) the actual parameter names `streamable_http_client` accepts, (b) whether it needs an `httpx.AsyncClient` (this project's existing dependency, already in `requirements.txt`) or something else. If it really does need a different HTTP client package, add that package to `requirements.txt` with whatever version `pip` resolves and note this prominently in your report — do not silently assume `httpx` works if the installed SDK says otherwise.

- [ ] **Step 2: Add settings**

Edit `UNS_DASHBOARD/backend/app/config.py` — add to the `Settings` class:
```python
    mcp_server_url: str = "http://uns_mcp_server:8000/mcp"
    mcp_api_key: str = ""
    llm_provider_type: str = "none"
    llm_base_url: str = "http://uns_ollama:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:14b-instruct"
```
(The `llm_*` settings are added here now since `config.py` is a single shared file — Task 3's/Task 6's code will read them from the same `Settings` instance Task 4 extends.)

- [ ] **Step 3: Write the failing tests**

```python
# UNS_DASHBOARD/backend/tests/test_mcp_client.py
import os

import pytest

from app.services import mcp_client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL")
MCP_API_KEY = os.environ.get("MCP_API_KEY")

pytestmark = pytest.mark.skipif(
    not MCP_SERVER_URL or not MCP_API_KEY,
    reason="MCP_SERVER_URL and MCP_API_KEY must both be set to a live UNS_MCP instance",
)


@pytest.fixture(autouse=True)
def _configure(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "mcp_server_url", MCP_SERVER_URL)
    monkeypatch.setattr(settings, "mcp_api_key", MCP_API_KEY)


@pytest.mark.asyncio
async def test_list_read_tools_returns_all_four_uns_mcp_tools():
    tools = await mcp_client.list_read_tools()
    names = {t["function"]["name"] for t in tools}
    assert names == {"get_current_value", "get_historical_trend", "list_signals", "list_active_alarms"}
    for t in tools:
        assert t["type"] == "function"
        assert "parameters" in t["function"]


@pytest.mark.asyncio
async def test_call_read_tool_returns_structured_content_for_list_signals():
    result = await mcp_client.call_read_tool("list_signals", {"topic_prefix": ""})
    assert isinstance(result, (list, dict))


@pytest.mark.asyncio
async def test_call_read_tool_raises_for_a_not_found_signal():
    with pytest.raises(Exception):
        await mcp_client.call_read_tool("get_current_value", {"topic": "pytest/nope", "signal_key": "nope"})


@pytest.mark.asyncio
async def test_wrong_api_key_fails(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "mcp_api_key", "definitely-wrong-key")
    with pytest.raises(Exception):
        await mcp_client.list_read_tools()
```

- [ ] **Step 4: Run tests to verify they fail**

Run (from `UNS_DASHBOARD/backend/`, with `MCP_SERVER_URL=http://localhost:8095/mcp` and `MCP_API_KEY=<the real UNS_MCP key>` exported): `pytest tests/test_mcp_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.mcp_client'`

- [ ] **Step 5: Implement `mcp_client.py`**

Write this using whatever Step 1 confirmed for header attachment. The shape below assumes `httpx.AsyncClient` is correct (this project's existing dependency) — adjust if Step 1's investigation found otherwise, and note the change:

```python
# UNS_DASHBOARD/backend/app/services/mcp_client.py
"""Thin MCP-client wrapper around UNS_MCP's four read tools.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 1 and Section 4.
"""
from __future__ import annotations

from typing import Any

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from app.config import settings


async def list_read_tools() -> list[dict]:
    async with httpx.AsyncClient(headers={"X-MCP-API-Key": settings.mcp_api_key}) as http_client:
        transport = streamable_http_client(settings.mcp_server_url, http_client=http_client)
        async with Client(transport) as client:
            result = await client.list_tools()
            return [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in result.tools
            ]


async def call_read_tool(name: str, arguments: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(headers={"X-MCP-API-Key": settings.mcp_api_key}) as http_client:
        transport = streamable_http_client(settings.mcp_server_url, http_client=http_client)
        async with Client(transport) as client:
            result = await client.call_tool(name, arguments)
            if result.is_error:
                text = " ".join(b.text for b in result.content if hasattr(b, "text"))
                raise RuntimeError(text or f"MCP tool {name} failed")
            return result.structured_content
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_mcp_client.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 7: Commit**

```bash
git add app/services/mcp_client.py app/config.py requirements.txt tests/test_mcp_client.py
git commit -m "feat(uns-dashboard): add MCP client wrapper for UNS_MCP read tools"
```

---

## Task 5: Extract dashboard/chart write logic into reusable services

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/dashboard_service.py`
- Create: `UNS_DASHBOARD/backend/app/services/chart_service.py`
- Modify: `UNS_DASHBOARD/backend/app/routers/dashboards.py`
- Modify: `UNS_DASHBOARD/backend/app/routers/charts.py`

**Interfaces:**
- Produces: `dashboard_service.create_dashboard(db, name, description=None) -> Dashboard`, `dashboard_service.publish_dashboard(db, dashboard_id) -> Dashboard` (raises `HTTPException(404)` if missing — same exception type the router already raises, so behavior is identical whether raised in the router or the service); `chart_service.create_chart(db, dashboard_id, data: dict) -> Chart`, `chart_service.update_chart(db, chart_id, updates: dict) -> Chart`, `chart_service.delete_chart(db, chart_id) -> None`.

**This task changes NO observable behavior.** It moves logic that currently lives inline in the routers into standalone functions the routers then call — purely so Task 6's chat agent can call the exact same logic without going through HTTP. Every existing test in `tests/test_dashboards_router.py` and `tests/test_charts_router.py` must pass completely unmodified after this refactor — that is this task's primary acceptance criterion, more important than anything else here.

- [ ] **Step 1: Write `dashboard_service.py`**

```python
# UNS_DASHBOARD/backend/app/services/dashboard_service.py
"""Dashboard write operations, shared by the REST router and the chat
agent's write tools. Extracted from app/routers/dashboards.py so both
callers run the exact same logic.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 4.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard


async def create_dashboard(db: AsyncSession, name: str, description: str | None = None) -> Dashboard:
    dashboard = Dashboard(name=name, description=description)
    db.add(dashboard)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard


async def publish_dashboard(db: AsyncSession, dashboard_id: str) -> Dashboard:
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    dashboard.status = "published"
    dashboard.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dashboard)
    return dashboard
```

- [ ] **Step 2: Write `chart_service.py`**

```python
# UNS_DASHBOARD/backend/app/services/chart_service.py
"""Chart write operations, shared by the REST router and the chat
agent's write tools. Extracted from app/routers/charts.py.

See docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 4.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.models.dashboard import Chart, ChartSignal, Dashboard


async def create_chart(db: AsyncSession, dashboard_id: str, data: dict) -> Chart:
    dashboard = await db.get(Dashboard, dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    data = dict(data)
    signals_data = data.pop("signals", [])
    chart = Chart(dashboard_id=dashboard_id, **data)
    chart.signals = [ChartSignal(**s) for s in signals_data]
    db.add(chart)
    await db.commit()
    return await _get_chart_with_signals(db, chart.id)


async def update_chart(db: AsyncSession, chart_id: str, updates: dict) -> Chart:
    result = await db.execute(select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals)))
    chart = result.scalar_one_or_none()
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")

    updates = dict(updates)
    signals_data = updates.pop("signals", None)
    for field, value in updates.items():
        setattr(chart, field, value)

    if signals_data is not None:
        chart.signals.clear()
        await db.flush()
        chart.signals = [ChartSignal(chart_id=chart_id, **s) for s in signals_data]

    await db.commit()
    return await _get_chart_with_signals(db, chart_id)


async def delete_chart(db: AsyncSession, chart_id: str) -> None:
    chart = await db.get(Chart, chart_id)
    if not chart:
        raise HTTPException(status_code=404, detail="Chart not found")
    await db.delete(chart)
    await db.commit()


async def _get_chart_with_signals(db: AsyncSession, chart_id: str) -> Chart:
    result = await db.execute(select(Chart).where(Chart.id == chart_id).options(selectinload(Chart.signals)))
    return result.scalar_one()
```

- [ ] **Step 3: Refactor `routers/dashboards.py` to call the service**

Replace the bodies of `create_dashboard` and `publish_dashboard` in `UNS_DASHBOARD/backend/app/routers/dashboards.py`:
```python
from app.services import dashboard_service

@router.post("/", response_model=DashboardRead, status_code=201)
async def create_dashboard(body: DashboardCreate, db: AsyncSession = Depends(get_db)):
    return await dashboard_service.create_dashboard(db, body.name, body.description)
```
```python
@router.post("/{dashboard_id}/publish", response_model=DashboardRead)
async def publish_dashboard(dashboard_id: str, db: AsyncSession = Depends(get_db)):
    return await dashboard_service.publish_dashboard(db, dashboard_id)
```
Leave every other route in this file (`list_dashboards`, `get_dashboard`, `update_dashboard`, `delete_dashboard`) exactly as-is — only `create_dashboard` and `publish_dashboard` have logic worth sharing with the chat agent per the tool surface in the spec.

- [ ] **Step 4: Refactor `routers/charts.py` to call the service**

Replace the bodies in `UNS_DASHBOARD/backend/app/routers/charts.py`:
```python
from app.services import chart_service

@router.post("/dashboards/{dashboard_id}/charts/", response_model=ChartRead, status_code=201)
async def create_chart(dashboard_id: str, body: ChartCreate, db: AsyncSession = Depends(get_db)):
    return await chart_service.create_chart(db, dashboard_id, body.model_dump())


@router.patch("/charts/{chart_id}", response_model=ChartRead)
async def update_chart(chart_id: str, body: ChartUpdate, db: AsyncSession = Depends(get_db)):
    return await chart_service.update_chart(db, chart_id, body.model_dump(exclude_unset=True))


@router.delete("/charts/{chart_id}", status_code=204)
async def delete_chart(chart_id: str, db: AsyncSession = Depends(get_db)):
    await chart_service.delete_chart(db, chart_id)
```
Remove the now-unused `_get_chart_with_signals` helper and its imports from this file (it moved to `chart_service.py`) — but check first whether anything else in this file still references it before deleting.

Note: `body.model_dump()` for `ChartCreate` includes the `signals` field as a list of dicts (from `ChartSignalCreate` sub-models) — confirm `chart_service.create_chart`'s `ChartSignal(**s)` construction still works with plain dicts the same way the original inline code's `ChartSignal(**s.model_dump())` did (it should, since `model_dump()` on the parent already recursively dumps nested models — verify with the tests in the next step rather than assuming).

- [ ] **Step 5: Run the full existing test suite — this is the acceptance gate for this task**

Run: `pytest tests/test_dashboards_router.py tests/test_charts_router.py -v`
Expected: PASS, identically to before this refactor (same test count, same assertions, zero behavior change). If anything fails, the refactor introduced a behavior difference — fix the service function to match the original inline behavior exactly, do not change the tests to match the new behavior.

Then run the whole suite: `pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/dashboard_service.py app/services/chart_service.py app/routers/dashboards.py app/routers/charts.py
git commit -m "refactor(uns-dashboard): extract dashboard/chart writes into reusable services"
```

---

## Task 6: The tool-calling loop (`chat_agent.py`)

**Files:**
- Create: `UNS_DASHBOARD/backend/app/services/chat_agent.py`
- Create: `UNS_DASHBOARD/backend/tests/test_chat_agent.py`

**Interfaces:**
- Consumes: `app.services.llm_providers.base.LLMProvider`/`ProviderResponse`/`ToolCall` (Task 3), `app.services.mcp_client` (Task 4), `app.services.dashboard_service`/`chart_service` (Task 5).
- Produces: `async def run_turn(db, provider, history: list[dict], user_message: str) -> tuple[str, list[dict], str | None, list[str]]` — returns `(reply_text, new_messages_to_persist, dashboard_id_if_now_known, action_summaries)`.

- [ ] **Step 1: Write the failing tests**

```python
# UNS_DASHBOARD/backend/tests/test_chat_agent.py
import pytest

from app.database import AsyncSessionLocal, create_tables
from app.services import chat_agent
from app.services.llm_providers.base import ProviderResponse, ToolCall


class _ScriptedProvider:
    """Replays a fixed sequence of responses, one per call to send()."""

    def __init__(self, responses: list[ProviderResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[list[dict], list[dict]]] = []

    async def send(self, messages, tools):
        self.calls.append((messages, tools))
        return self._responses.pop(0)


@pytest.fixture
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
```

Note: every test above passes `read_tools=[]` explicitly — `run_turn` accepts an optional `read_tools` parameter that, when omitted, defaults to calling the real `mcp_client.list_read_tools()` (a live network call). Passing `[]` here means these tests never need a live `UNS_MCP` instance; only Task 9's end-to-end verification exercises the real default path.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `UNS_DASHBOARD/backend/`): `pytest tests/test_chat_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.chat_agent'`

- [ ] **Step 3: Implement `chat_agent.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_agent.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Run the full test suite so far**

Run: `pytest tests/ -v`
Expected: PASS across all tasks so far (the MCP-client and Ollama-dependent tests from Tasks 3-4 skip cleanly if those env vars aren't set in this shell; that's expected — Task 9 does full end-to-end wiring).

- [ ] **Step 6: Commit**

```bash
git add app/services/chat_agent.py tests/test_chat_agent.py
git commit -m "feat(uns-dashboard): add the provider-agnostic tool-calling loop"
```

---

## Task 7: Chat HTTP router

**Files:**
- Create: `UNS_DASHBOARD/backend/app/routers/chat.py`
- Modify: `UNS_DASHBOARD/backend/app/main.py`
- Create: `UNS_DASHBOARD/backend/tests/test_chat_router.py`

**Interfaces:**
- Consumes: `chat_agent.run_turn` (Task 6), `ChatSession`/`ChatMessage` (Task 2), `Settings` (Task 4's additions).
- Produces: `GET /chat/status`, `POST /chat/sessions`, `POST /chat/sessions/{id}/messages`, `GET /chat/sessions/{id}`.

- [ ] **Step 1: Write the failing tests**

```python
# UNS_DASHBOARD/backend/tests/test_chat_router.py
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.config import settings


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_status_reports_unavailable_when_no_provider_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider_type", "none")
    response = await client.get("/chat/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"]


@pytest.mark.asyncio
async def test_create_session_returns_an_id(client):
    response = await client.post("/chat/sessions")
    assert response.status_code == 201
    assert "id" in response.json()


@pytest.mark.asyncio
async def test_get_session_returns_empty_history_for_a_new_session(client):
    created = await client.post("/chat/sessions")
    session_id = created.json()["id"]

    response = await client.get(f"/chat/sessions/{session_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["dashboard_id"] is None
    assert body["messages"] == []


@pytest.mark.asyncio
async def test_get_unknown_session_returns_404(client):
    response = await client.get("/chat/sessions/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_returns_503_when_provider_unavailable(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider_type", "none")
    created = await client.post("/chat/sessions")
    session_id = created.json()["id"]

    response = await client.post(f"/chat/sessions/{session_id}/messages", json={"message": "hola"})
    assert response.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `UNS_DASHBOARD/backend/`): `pytest tests/test_chat_router.py -v`
Expected: FAIL (404s, since the router doesn't exist yet — `app.main` doesn't register it).

- [ ] **Step 3: Implement `chat.py`**

```python
# UNS_DASHBOARD/backend/app/routers/chat.py
"""The chat HTTP surface. See
docs/superpowers/specs/2026-09-05-uns-dashboard-chat-agent-design.md,
Section 3.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionCreated,
    ChatSessionRead,
    ChatStatus,
)
from app.services import chat_agent
from app.services.llm_providers.openai_compatible import OpenAICompatibleProvider

router = APIRouter(prefix="/chat", tags=["chat"])


def _build_provider():
    if settings.llm_provider_type == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key, model=settings.llm_model
        )
    return None


@router.get("/status", response_model=ChatStatus)
async def chat_status():
    if settings.llm_provider_type == "none":
        return ChatStatus(available=False, provider_type=None, reason="No LLM provider configured")

    if settings.llm_provider_type == "openai_compatible":
        # Assumes the endpoint exposes the standard OpenAI /v1/models path
        # (true for Ollama's compat layer per its docs, and for vLLM/OpenAI/
        # OpenRouter) -- verify with a real curl against whatever LLM_BASE_URL
        # is actually configured before trusting this in Task 9's live check;
        # if it 404s against a real target, swap to a lighter probe (e.g. a
        # bare TCP connect, or that endpoint's actual health path).
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                resp = await http_client.get(settings.llm_base_url.rstrip("/") + "/models")
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return ChatStatus(available=False, provider_type="openai_compatible", reason=f"Provider unreachable: {exc}")
        return ChatStatus(available=True, provider_type="openai_compatible", reason=None)

    return ChatStatus(available=False, provider_type=settings.llm_provider_type, reason="Provider type not yet implemented")


@router.post("/sessions", response_model=ChatSessionCreated, status_code=201)
async def create_session(db: AsyncSession = Depends(get_db)):
    session = ChatSession()
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionCreated(id=session.id)


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id).options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSessionRead(dashboard_id=session.dashboard_id, messages=session.messages)


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(session_id: str, body: ChatMessageRequest, db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    provider = _build_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail="No LLM provider is available")

    history_result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    history = [m.content for m in history_result.scalars().all()]

    try:
        reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(db, provider, history, body.message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"LLM provider failed: {exc}") from exc

    for msg in new_messages:
        db.add(ChatMessage(session_id=session_id, role=msg["role"], content=msg))

    if dashboard_id and not session.dashboard_id:
        session.dashboard_id = dashboard_id

    await db.commit()

    return ChatMessageResponse(reply=reply, dashboard_id=session.dashboard_id, actions=actions)
```

- [ ] **Step 4: Register the router in `main.py`**

Edit `UNS_DASHBOARD/backend/app/main.py`:
```python
from app.routers import chat, dashboards, charts, history, signals, stream
```
```python
app.include_router(chat.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_chat_router.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/routers/chat.py app/main.py tests/test_chat_router.py
git commit -m "feat(uns-dashboard): add chat HTTP router"
```

---

## Task 8: Frontend chat panel

**Files:**
- Modify: `UNS_DASHBOARD/frontend/src/api/client.ts`
- Modify: `UNS_DASHBOARD/frontend/src/types/dashboard.ts`
- Create: `UNS_DASHBOARD/frontend/src/components/editor/ChatPanel.tsx`
- Modify: `UNS_DASHBOARD/frontend/src/pages/EditorPage.tsx`

**Interfaces:**
- Produces: a chat panel visible in the dashboard editor, backed by the Task 7 endpoints.

- [ ] **Step 1: Add chat types**

Append to `UNS_DASHBOARD/frontend/src/types/dashboard.ts`:
```typescript
export interface ChatStatus {
  available: boolean;
  provider_type: string | null;
  reason: string | null;
}

export interface ChatMessage {
  role: string;
  content: Record<string, unknown>;
}

export interface ChatSessionDetail {
  dashboard_id: string | null;
  messages: ChatMessage[];
}

export interface ChatMessageResult {
  reply: string;
  dashboard_id: string | null;
  actions: string[];
}
```

- [ ] **Step 2: Add chat API client calls**

Add to the `api` object in `UNS_DASHBOARD/frontend/src/api/client.ts`:
```typescript
import type { ChatMessageResult, ChatSessionDetail, ChatStatus, /* existing imports */ } from "../types/dashboard";
```
```typescript
  chat: {
    status: () => http.get<ChatStatus>("/chat/status").then((r) => r.data),
    createSession: () => http.post<{ id: string }>("/chat/sessions").then((r) => r.data),
    getSession: (id: string) => http.get<ChatSessionDetail>(`/chat/sessions/${id}`).then((r) => r.data),
    sendMessage: (sessionId: string, message: string) =>
      http.post<ChatMessageResult>(`/chat/sessions/${sessionId}/messages`, { message }).then((r) => r.data),
  },
```

- [ ] **Step 3: Write `ChatPanel.tsx`**

```tsx
// UNS_DASHBOARD/frontend/src/components/editor/ChatPanel.tsx
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { ChatMessage } from "../../types/dashboard";

export function ChatPanel({ onDashboardCreated }: { onDashboardCreated: (dashboardId: string) => void }) {
  const [status, setStatus] = useState<{ available: boolean; reason: string | null } | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.chat.status().then(setStatus).catch(() => setStatus({ available: false, reason: "No se pudo comprobar el estado del asistente." }));
  }, []);

  useEffect(() => {
    if (status?.available && !sessionId) {
      api.chat.createSession().then((s) => setSessionId(s.id));
    }
  }, [status, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!sessionId || !input.trim() || sending) return;
    const userText = input;
    setInput("");
    setSending(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: { text: userText } }]);
    try {
      const result = await api.chat.sendMessage(sessionId, userText);
      setMessages((m) => [...m, { role: "assistant", content: { text: result.reply } }]);
      if (result.dashboard_id) onDashboardCreated(result.dashboard_id);
    } catch {
      setError("El asistente no respondió. Inténtalo de nuevo.");
    } finally {
      setSending(false);
    }
  };

  if (!status) return <div className="p-4 text-sm text-ink-muted">Comprobando el asistente…</div>;

  if (!status.available) {
    return (
      <div className="p-4 text-sm text-ink-muted border border-border rounded-lg">
        Asistente no disponible{status.reason ? ` — ${status.reason}` : ""}.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full border border-border rounded-lg">
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {messages.map((m, i) => (
          <div key={i} className={`text-sm rounded-lg px-3 py-2 max-w-[85%] ${m.role === "user" ? "self-end bg-brand text-white" : "self-start bg-surface"}`}>
            {String(m.content.text ?? "")}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {error && <div className="px-3 text-xs text-danger">{error}</div>}
      <div className="flex gap-2 p-3 border-t border-border">
        <input
          className="flex-1 border border-border rounded-lg px-3 py-2 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Describe el dashboard que quieres…"
          disabled={sending}
        />
        <button className="px-4 py-2 text-sm rounded-lg bg-brand text-white disabled:opacity-50" onClick={send} disabled={sending}>
          Enviar
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Mount it in `EditorPage.tsx`**

Add the import and render `<ChatPanel onDashboardCreated={(id) => navigate(`/dashboards/${id}/edit`)} />` somewhere in the editor's layout (a sidebar panel alongside the existing forms is reasonable — match whatever layout structure `GridWorkspace`/`DashboardMetaForm` already use in this file; this is a placement detail for you to fit sensibly into the existing JSX, not a fixed requirement).

- [ ] **Step 5: Verify the frontend builds**

```bash
cd UNS_DASHBOARD/frontend
npm run build
```
Expected: builds without TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add src/api/client.ts src/types/dashboard.ts src/components/editor/ChatPanel.tsx src/pages/EditorPage.tsx
git commit -m "feat(uns-dashboard): add chat panel to the dashboard editor"
```

---

## Task 9: Wiring, deployment, and end-to-end verification

**Files:**
- Modify: `UNS_DASHBOARD/docker-compose.yml`
- Modify: `UNS_DASHBOARD/.env.example` (or backend-specific `.env.example` if this repo keeps one per service — check which exists)
- Modify: `docker-compose.yml` (repo root)

**Interfaces:**
- Produces: a fully wired, live-verified chat feature across both the Ollama pilot and the full `UNS_DASHBOARD` ↔ `UNS_MCP` ↔ `UNS_SILVER` chain.

- [ ] **Step 1: Add the new env vars to `UNS_DASHBOARD`'s backend service**

Edit `UNS_DASHBOARD/docker-compose.yml`'s `dashboard_backend` service — add to its `environment:` block:
```yaml
      MCP_SERVER_URL: ${MCP_SERVER_URL:-http://uns_mcp_server:8000/mcp}
      MCP_API_KEY: ${MCP_API_KEY:-}
      LLM_PROVIDER_TYPE: ${LLM_PROVIDER_TYPE:-none}
      LLM_BASE_URL: ${LLM_BASE_URL:-http://uns_ollama:11434/v1}
      LLM_API_KEY: ${LLM_API_KEY:-ollama}
      LLM_MODEL: ${LLM_MODEL:-qwen2.5:14b-instruct}
```
`dashboard_backend` already joins `uns_manager_net` (confirmed during planning) — the same network `uns_mcp_server` and `uns_ollama` are on — so no network changes are needed, only these environment additions.

- [ ] **Step 2: Update the `.env.example`**

Add the same variables (with the same defaults) to whichever `.env.example` this stack actually uses for `dashboard_backend`'s configuration — check the existing file first, don't create a duplicate.

- [ ] **Step 3: Wire `UNS_OLLAMA` into the root `docker-compose.yml`**

Add `- UNS_OLLAMA/docker-compose.yml` to the root `docker-compose.yml`'s `include:` list, and update the header comment's stack list, following the exact pattern of the `UNS_SILVER`/`UNS_MCP` entries already there.

- [ ] **Step 4: Validate**

```bash
docker compose config
```
(From the repo root — parse-only, safe. Do not run `docker compose up` from the repo root if another checkout's stack is already running under the same project name — verify standalone via each module's own `docker compose up` instead, same discipline as every prior task in this project.)

- [ ] **Step 5: Bring up the real chain and set a real API key**

```bash
cd UNS_DASHBOARD
# set MCP_API_KEY in .env to UNS_MCP's actual configured key, LLM_PROVIDER_TYPE=openai_compatible
docker compose up -d --build dashboard_backend
curl -s http://localhost:8001/chat/status
```
Expected: `{"available": true, "provider_type": "openai_compatible", "reason": null}` — if `false`, check `uns_ollama`'s and `uns_mcp_server`'s reachability from inside `uns_dashboard_backend` (`docker exec uns_dashboard_backend curl -s http://uns_ollama:11434/v1/models`) before assuming the code is wrong.

- [ ] **Step 6: End-to-end conversation test**

```bash
SESSION=$(curl -s -X POST http://localhost:8001/chat/sessions | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST http://localhost:8001/chat/sessions/$SESSION/messages \
  -H "Content-Type: application/json" \
  -d '{"message": "Crea un dashboard llamado Prueba Piloto y añade una gráfica con la señal Gen_RPM_Avg si existe"}'
```
Expected: a real reply, `dashboard_id` populated, `actions` listing at least a `create_dashboard(...)` call (and `add_chart(...)` if a matching signal was actually found via `list_signals` — if none exists in the live `UNS_SILVER` data, the model should say so rather than inventing one; check the actual reply text and judge whether this happened correctly, don't just check the HTTP status).

Then confirm the dashboard is real and renders normally:
```bash
curl -s http://localhost:8001/dashboards/<the returned dashboard_id>
```
And open it in the actual frontend (`http://localhost:3002`) to visually confirm the editor shows what the chat created — this is the real proof the write path works end to end, not just that the API returned 200.

- [ ] **Step 7: Verify graceful degradation**

```bash
cd UNS_OLLAMA && docker compose stop
curl -s http://localhost:8001/chat/status
```
Expected: `available: false` now that Ollama is down. Restart it afterward: `cd UNS_OLLAMA && docker compose start`.

- [ ] **Step 8: Commit**

```bash
cd G:/00_data/00_Formacion/INARI_V05
git add UNS_DASHBOARD/docker-compose.yml UNS_DASHBOARD/.env.example docker-compose.yml
git commit -m "feat(uns-dashboard): wire chat agent's env vars and UNS_OLLAMA into the stack"
```
