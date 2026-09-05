# UNS Dashboard — Chat Agent Design Spec
**Date:** 2026-09-05
**Status:** Draft — pending user review
**Scope:** First milestone — an opt-in chat panel inside `UNS_DASHBOARD` that creates and edits dashboards from natural-language requests, via a provider-agnostic LLM agent piloted on a local Ollama instance. Third and final sub-project of the LLM/agent roadmap (`UNS_HISTORIAN` → `UNS_SILVER` → `UNS_MCP` → this).

---

## Context

`UNS_MCP` (previous milestone) gave any LLM/agent read-only access to `UNS_SILVER`'s data. This milestone is the write side: "ayúdame a generar un dashboard mediante un chatbot" — a conversational assistant, embedded in `UNS_DASHBOARD`'s own UI, that calls the CRUD API `UNS_DASHBOARD` already has (`POST /dashboards/`, `POST /dashboards/{id}/charts/`, etc. — all implemented and tested) on the user's behalf.

Two things distinguish this from `UNS_MCP`:
- **It writes.** Unlike `UNS_MCP`'s "read-only, full stop" boundary, this agent creates/edits real dashboards. Its write actions are therefore custom, in-process tool calls against `UNS_DASHBOARD`'s own trusted backend code — not exposed over MCP to arbitrary external agents.
- **It must support multiple LLM providers from day one**, piloted on a locally-hosted Ollama model (the user has a machine with an RTX 5090 and wants a self-hosted pilot before committing to any cloud provider), with OpenAI, OpenRouter, Claude, and a remote DGX Spark (running Ollama or vLLM) all as near-term destinations. This is why the agent cannot rely on any single provider's native conveniences (e.g. Anthropic's server-side MCP connector, which only exists for Claude) — the tool-calling loop must be implemented once, by this project, and driven uniformly regardless of which provider answers it.

This is an **additional, opt-in mode** — it changes nothing about `UNS_DASHBOARD`'s existing editor, viewer, or API. A user who never opens the chat panel sees no difference at all.

---

## Key Decisions (from clarifying questions)

| Decision | Choice |
|---|---|
| Where the chat lives | Inside `UNS_DASHBOARD`'s own frontend/backend — not a separate app, not "talk to Claude Desktop instead." A new chat panel in the product itself |
| Provider abstraction | Two adapter *types*, not one per named provider: `openai_compatible` (covers Ollama — local or on the DGX Spark —, vLLM on the DGX Spark, OpenAI, and OpenRouter, since they all speak the same chat-completions/tool-calling shape) and `anthropic` (Claude's distinct Messages API shape). Switching providers within a type is pure configuration (`base_url`/`api_key`/`model`), no code change |
| Pilot provider | `openai_compatible` pointed at a new local `ollama` container, model `qwen2.5:14b-instruct` (configurable) — chosen for reliable tool-calling at a size that runs fast on a single RTX 5090 |
| Tool execution model | Since no provider-native mechanism (like Claude's MCP connector) works uniformly across all four target providers, `UNS_DASHBOARD`'s backend runs the tool-calling loop itself: it is an **MCP client** of `UNS_MCP` for the four read tools, and executes the write tools **directly, in-process**, against its own existing CRUD code |
| Write tool surface | `create_dashboard`, `add_chart`, `update_chart`, `delete_chart`, `publish_dashboard`. **No `delete_dashboard`** — destroying an entire dashboard requires the existing UI, never a chat message alone |
| Scope of write actions | Draft dashboards only — matches `UNS_DASHBOARD`'s existing rule that a published dashboard is a read-only view; the chat is part of the editing experience, never the viewer |
| Conversation model | Iterative, with persisted context — a chat is a session, associated with at most one dashboard (`NULL` until the first successful `create_dashboard` call binds it), so "add another chart" or "change the color" naturally refers to the dashboard already being discussed |
| No-provider behavior | If no provider is configured/reachable, the chat simply cannot be used — the frontend disables the message input with a clear reason, rather than a broken or silently-failing chat. A provider that stops responding mid-session returns a clear error (503) instead of hanging or crashing the page |
| Anthropic adapter | Only the interface is defined this milestone — no working implementation yet. Activated when Claude is actually wanted as an option, not before |
| Response delivery | Synchronous request/response for v1 (send a message, wait, get the reply + resulting dashboard changes) — no streaming yet |

---

## Section 1 — Architecture

Two new pieces:

- **`UNS_OLLAMA/`** — a new sibling module, own `docker-compose.yml`/`.env.example`/`scripts/`, containing exactly one container: `ollama` (official image), with GPU passthrough (`deploy.resources.reservations.devices`, `nvidia-container-toolkit` already present on the host per this project's own confirmation) and a named volume for downloaded models. Joins the shared external network so `UNS_DASHBOARD`'s backend can reach it at `http://ollama:11434`. No other module needs a container here — a cloud provider or the DGX Spark are reached over the network as external endpoints, never dockerized in this repo.

- **New code inside `UNS_DASHBOARD/backend`** (not a separate module — it needs the same DB session as the existing dashboard/chart CRUD):
  - `app/routers/chat.py` — the chat HTTP surface.
  - `app/services/chat_agent.py` — the tool-calling loop.
  - `app/services/llm_providers/` — the provider abstraction (`base.py` defines the interface; `openai_compatible.py` implements it; `anthropic.py` is scaffolded, not implemented).
  - `app/services/mcp_client.py` — a thin wrapper around the `mcp` SDK's client mode, calling `UNS_MCP`'s four read tools.
  - `app/models/chat.py` / `app/schemas/chat.py` — new DB models/schemas for sessions and messages.

```
UNS_DASHBOARD backend
  chat_agent.py ── loop: build history → call provider → execute tool calls → repeat until done
       │
       ├─► mcp_client.py ──────────► UNS_MCP (read: list_signals, get_current_value,
       │                              get_historical_trend, list_active_alarms)
       │
       ├─► existing CRUD (in-process, same DB session) (write: create_dashboard,
       │                              add_chart, update_chart, delete_chart, publish_dashboard)
       │
       └─► llm_providers/ ─────────► ollama (pilot) | DGX Spark (Ollama/vLLM) | OpenAI |
                                      OpenRouter | Claude (future)
```

The provider interface (`llm_providers/base.py`) is deliberately small — one method to send a conversation (message history + available tool definitions) and get back either a final assistant text reply or one-or-more tool calls to execute:

```python
class LLMProvider(Protocol):
    async def send(self, messages: list[dict], tools: list[dict]) -> ProviderResponse: ...
```
`ProviderResponse` normalizes whatever shape the underlying provider returns (OpenAI-style `tool_calls` array vs. Anthropic-style `tool_use` content blocks) into one common shape the rest of `chat_agent.py` works with, so the loop itself never branches on provider type.

---

## Section 2 — Data Model (`UNS_DASHBOARD`'s existing Postgres)

```sql
CREATE TABLE chat_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id VARCHAR(36) REFERENCES dashboards(id) ON DELETE CASCADE,  -- NULL until first create_dashboard succeeds
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,          -- 'user' | 'assistant' | 'tool'
    content    JSONB NOT NULL,         -- the message in the *provider's own* wire format, for exact replay
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chat_messages_session_time ON chat_messages (session_id, created_at);
```

Storing `content` in the provider's own format (rather than a normalized shape) means the exact conversation — including tool_use/tool_result blocks — can be replayed to the provider on the next turn without lossy reconstruction. Since a session is pinned to one provider type for its lifetime in this milestone (no mid-conversation provider switching), this isn't ambiguous.

---

## Section 3 — HTTP Surface (new router in `UNS_DASHBOARD/backend`)

```
GET  /chat/status
     → { "available": bool, "provider_type": "openai_compatible" | "anthropic" | null, "reason": str | null }
     Self-hosted providers (openai_compatible pointed at Ollama/vLLM): actually pings the endpoint
     (e.g. Ollama's /api/tags) to confirm it's reachable and the configured model exists.
     Cloud providers: only checks that an API key is configured (no live call, to avoid burning
     a request just for a health check).

POST /chat/sessions
     → { "id": uuid }
     Creates a new session with dashboard_id = NULL.

POST /chat/sessions/{id}/messages
     body: { "message": str }
     → { "reply": str, "dashboard_id": str | null, "actions": [...] }
     Appends the user message, runs the tool-calling loop to completion (bounded — see Section 4),
     appends the assistant's turns (including any tool calls/results), returns the final text reply,
     the session's dashboard_id (now non-null if a dashboard was created this turn), and a summary
     of what write actions were taken (for the frontend to show "created chart X" style confirmations).
     Returns 503 if the configured provider doesn't respond.

GET  /chat/sessions/{id}
     → { "dashboard_id": str | null, "messages": [...] }
     Full history, for reloading the panel.
```

---

## Section 4 — The Tool-Calling Loop (`chat_agent.py`)

1. Load the session's message history (Section 2's `chat_messages`, in the provider's wire format).
2. Append the new user message.
3. Call the configured `LLMProvider.send(messages, tools)`, where `tools` is the fixed set of 5 write-tool definitions plus the 4 read-tool definitions (fetched once from `UNS_MCP`'s tool listing via the MCP client, not hand-duplicated).
4. If the response is a final text reply: persist it, return it to the caller. Done.
5. If the response includes tool calls: for each one, dispatch to either the MCP client (read tools) or the in-process CRUD service (write tools), collect results, persist the assistant's tool-call turn and the tool-result turn, and go back to step 3 with the updated history.
6. **Bounded loop**: a hard cap (e.g. 8 iterations) prevents a misbehaving model from looping forever; hitting the cap returns a clear "I couldn't finish this request" reply rather than hanging the request indefinitely.

A write tool's execution reuses the exact same service functions the existing REST routers already call (`app/routers/dashboards.py`, `app/routers/charts.py`) — the tool wrapper is a thin adapter turning the LLM's tool-call arguments into a call to that same code, inside the same request's DB session, so a create-then-add-chart-then-publish sequence in one turn is one transaction-consistent unit of work from the database's point of view (each step still commits as the existing CRUD functions already do — no distributed-transaction complexity introduced).

---

## Section 5 — Provider Adapters

**`openai_compatible`** (implemented, exercised against Ollama this milestone): speaks the OpenAI chat-completions wire format (`POST {base_url}/v1/chat/completions` or Ollama's native `/api/chat` with `tools`, depending on which the pilot settles on — verify against Ollama's current tool-calling docs before writing this adapter, not from memory, the same discipline this project applied to the MCP SDK). Configured via `LLM_BASE_URL`, `LLM_API_KEY` (blank/unused for local Ollama), `LLM_MODEL`.

**`anthropic`** (interface only): would use the official `anthropic` Python SDK's Messages API and tool-use shape (per this project's own `claude-api` conventions when it's actually built) — not implemented this milestone.

---

## Section 6 — Frontend

A new chat panel component in `UNS_DASHBOARD`'s existing editor UI (exact placement — a sidebar tab, a slide-over panel — is a frontend-design detail for the implementation plan, not fixed here). On mount, calls `GET /chat/status`; if unavailable, renders a disabled input with the reason text. Otherwise: a standard chat transcript UI, POSTing to `/chat/sessions/{id}/messages` per turn, and — once `dashboard_id` becomes non-null in a response — either navigating to that dashboard's editor or refreshing the current one to show the charts the agent just created.

---

## Section 7 — Deployment

```
UNS_OLLAMA/
  docker-compose.yml   -- one service, `ollama`, GPU passthrough, named volume for models
  .env.example
  scripts/{up,down,restart,logs,status}.sh
  README.md            -- includes how to pull qwen2.5:14b-instruct, and how to point
                           LLM_BASE_URL at the DGX Spark instead when that's ready
```

`UNS_DASHBOARD/backend` gains: the new router/services/models above, plus `.env` additions (`LLM_PROVIDER_TYPE`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `MCP_SERVER_URL`, `MCP_API_KEY`), plus a DB migration for `chat_sessions`/`chat_messages`, plus joining whatever network `UNS_OLLAMA`'s container is reachable on (the existing shared external network, same pattern as every other cross-module coupling in this project).

Root `docker-compose.yml` gains a sixth `include:` entry for `UNS_OLLAMA/docker-compose.yml`.

---

## Section 8 — Testing

- **Unit**: the `openai_compatible` adapter against a mocked HTTP response (deterministic — never depends on a real model's actual output); the tool-calling loop's dispatch logic (read tool → MCP client called; write tool → CRUD service called; loop terminates on final text reply; loop is bounded); each write tool wrapper against the existing DB test fixtures already used by `test_dashboards_router.py`/`test_charts_router.py`.
- **Integration**: the MCP client path against a live `UNS_MCP` instance (mirrors the dual-role pattern already established there — this project is now both an MCP *server* and, here, an MCP *client*); `GET /chat/status`'s live-ping behavior against a real (and a deliberately-stopped) Ollama container.
- **Manual, end-to-end**: with Ollama running and a model pulled, open the chat panel and hold a real multi-turn conversation that creates a dashboard, adds two charts referencing real Silver signals (discovered via a `list_signals` call the agent makes on its own), and publishes it — confirm the resulting dashboard renders correctly in the normal (non-chat) viewer, proving the chat path produced the same kind of data the manual editor would have.

---

## Explicitly deferred (future milestones)

- A working `anthropic` adapter (Claude as an actual selectable provider) — interface only for now.
- OpenAI and OpenRouter as configured, tested destinations — covered by the same `openai_compatible` adapter type once someone points `LLM_BASE_URL`/`LLM_API_KEY` at them, but not exercised or documented as a supported path this milestone.
- Real deployment against the DGX Spark — same adapter, different `LLM_BASE_URL`; deferred until that machine is available for testing.
- Streaming responses (typing-indicator / progressive tool-call visibility) — v1 is synchronous.
- `delete_dashboard` via chat — deliberately excluded from the tool surface, not just unimplemented.
- Multi-dashboard sessions (one chat managing several dashboards at once).
- Any chat-driven action while a dashboard is published (view-only) — the chat only ever operates on drafts, matching the existing editor/viewer split.
