# Chat Agent Signal Search & Candidate Disambiguation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the chat agent find a signal by name/keyword (not just by exact asset-path prefix) and, when ambiguous, let the user pick from clickable candidates instead of negotiating in free text.

**Architecture:** A new `search_signals(query, limit)` tool in `UNS_MCP` does case-insensitive substring matching across `signal_key`/`description`/`topic` (unlike `list_signals`' path-prefix-only filter). A new `present_signal_candidates` tool in the chat agent's tool-calling loop is intercepted specially: it never touches the database, ends the turn immediately, and surfaces its candidates as structured data through the whole stack (`run_turn` → `ChatMessageResponse` → `ChatPanel`) so the frontend can render them as one-click buttons instead of relying on free-text follow-up.

**Tech Stack:** Python 3.12, `psycopg` (UNS_MCP, sync), FastAPI + SQLAlchemy async + Pydantic (UNS_DASHBOARD backend), React + TypeScript + Vite (UNS_DASHBOARD frontend), Postgres/TimescaleDB.

## Global Constraints

- Spec: `UNS_DASHBOARD/docs/superpowers/specs/2026-09-06-chat-agent-signal-search-design.md` — read it first; it is the binding authority for anything this plan doesn't spell out.
- `search_signals` is parameterized SQL only (`%s`/`%(name)s` placeholders) — never string-interpolate `query` into SQL.
- `present_signal_candidates` is dispatched from `chat_agent.py`'s tool loop but is NOT a write tool (never touches `dashboard_service`/`chart_service`) and is NOT forwarded to MCP.
- All code/comments/commit messages in English; UI copy in Spanish (matches this app's existing locale).
- No migration tool exists in either `UNS_MCP` or `UNS_DASHBOARD/backend` — schema changes (there are none in this plan) would go through `Base.metadata.create_all`/raw SQL init scripts as established.
- Backend tests MUST use the isolated test databases (`uns_dashboard_test`, `uns_silver`'s existing `SILVER_DATABASE_URL`/`SEED_DATABASE_URL` test-role pattern) per `UNS_DASHBOARD/backend/tests/README.md` and `UNS_MCP/server/tests/test_db.py`'s existing skip-gate — never the real dev database.

---

### Task 1: `search_signals` tool in UNS_MCP

**Files:**
- Modify: `UNS_MCP/server/app/db.py`
- Modify: `UNS_MCP/server/app/server.py`
- Test: `UNS_MCP/server/tests/test_db.py`
- Test: `UNS_MCP/server/tests/test_server.py`

**Interfaces:**
- Produces: `db.search_signals(conn, query: str, limit: int = 10) -> list[dict]` (each dict: `{topic, signal_key, signal_type, unit, description, score}`), exposed as the MCP tool `search_signals(query: str, limit: int = 10) -> list[dict]`.

- [ ] **Step 1: Write the failing db-layer test**

Append to `UNS_MCP/server/tests/test_db.py` (uses the file's existing `conn` fixture — `seed_conn, reader_conn = conn`):

```python
def test_search_signals_matches_case_insensitively_across_topic_signal_key_and_description(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, unit, description, effective_since) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Max", "kpi", "rpm", "Maximum generator RPM", now),
    )
    seed_conn.commit()

    from app.db import search_signals

    # Matches via the topic segment, case-insensitively, even though it's not a prefix.
    result = search_signals(reader_conn, "generator")
    assert any(r["signal_key"] == "Gen_RPM_Max" for r in result)

    # Matches via signal_key substring.
    result = search_signals(reader_conn, "rpm_max")
    assert any(r["signal_key"] == "Gen_RPM_Max" for r in result)

    # Matches via description substring.
    result = search_signals(reader_conn, "maximum")
    assert any(r["signal_key"] == "Gen_RPM_Max" for r in result)


def test_search_signals_scores_signal_key_matches_above_description_only_matches(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, description, effective_since) "
        "VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Max", "kpi", "Peak generator speed", now),
    )
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, description, effective_since) "
        "VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T01/MOTOR", "Motor_Status", "raw", "Reports rpm in its notes field", now),
    )
    seed_conn.commit()

    from app.db import search_signals

    result = search_signals(reader_conn, "rpm")
    keys_in_order = [r["signal_key"] for r in result if r["signal_key"] in ("Gen_RPM_Max", "Motor_Status")]
    assert keys_in_order == ["Gen_RPM_Max", "Motor_Status"]


def test_search_signals_respects_limit_and_excludes_superseded_rows(conn):
    seed_conn, reader_conn = conn
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        seed_conn.execute(
            "INSERT INTO signal_catalog (topic, signal_key, signal_type, effective_since) VALUES (%s,%s,%s,%s)",
            (f"pytest/T0{i}/GENERATOR", f"Gen_RPM_{i}", "kpi", now),
        )
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, effective_since, effective_until) "
        "VALUES (%s,%s,%s,%s,%s)",
        ("pytest/T09/GENERATOR", "Gen_RPM_Superseded", "kpi", now, now),
    )
    seed_conn.commit()

    from app.db import search_signals

    result = search_signals(reader_conn, "rpm", limit=3)
    assert len(result) == 3
    assert not any(r["signal_key"] == "Gen_RPM_Superseded" for r in result)


def test_search_signals_returns_empty_list_for_no_match(conn):
    seed_conn, reader_conn = conn

    from app.db import search_signals

    assert search_signals(reader_conn, "pytest-nonexistent-keyword-xyz") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `UNS_MCP/server/`, with `SILVER_DATABASE_URL`/`SEED_DATABASE_URL` exported per this file's existing skip-gate): `pytest tests/test_db.py -k search_signals -v`
Expected: FAIL with `ImportError: cannot import name 'search_signals' from 'app.db'`

- [ ] **Step 3: Implement `db.search_signals`**

Add to `UNS_MCP/server/app/db.py` (near `list_signals`, same file's existing imports already cover everything needed — `psycopg`, `Any`):

```python
def search_signals(conn: psycopg.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Case-insensitive substring search across signal_key, description, and
    the full topic path -- unlike list_signals' path-PREFIX filter, this finds
    a signal by name or partial name regardless of where it sits in the
    asset hierarchy. Splits `query` into words; a row scores points for each
    word that matches signal_key (3), topic (2), or description (1), summed
    across words. Only currently-active rows (effective_until IS NULL) are
    considered."""
    words = [w for w in query.strip().split() if w]
    if not words:
        return []

    conditions: list[str] = []
    score_parts: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    for i, word in enumerate(words):
        key = f"w{i}"
        params[key] = f"%{word}%"
        conditions.append(f"(signal_key ILIKE %({key})s OR topic ILIKE %({key})s OR description ILIKE %({key})s)")
        score_parts.append(
            f"(CASE WHEN signal_key ILIKE %({key})s THEN 3 "
            f"WHEN topic ILIKE %({key})s THEN 2 "
            f"WHEN description ILIKE %({key})s THEN 1 ELSE 0 END)"
        )
    where_clause = " OR ".join(conditions)
    score_expr = " + ".join(score_parts)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT topic, signal_key, signal_type, unit, description, ({score_expr}) AS score
            FROM signal_catalog
            WHERE effective_until IS NULL AND ({where_clause})
            ORDER BY score DESC, topic, signal_key
            LIMIT %(limit)s
            """,
            params,
        )
        return [
            {"topic": r[0], "signal_key": r[1], "signal_type": r[2], "unit": r[3], "description": r[4], "score": r[5]}
            for r in cur.fetchall()
        ]
```

- [ ] **Step 4: Run the db-layer tests to verify they pass**

Run: `pytest tests/test_db.py -k search_signals -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Write the failing tool-layer test**

Append to `UNS_MCP/server/tests/test_server.py` (add `search_signals` to the existing import line):
```python
from app.server import get_current_value, get_historical_trend, list_active_alarms, list_signals, search_signals
```
Then:
```python
def test_search_signals_tool_finds_a_signal_by_keyword_not_prefix(seed_conn):
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
    seed_conn.execute(
        "INSERT INTO signal_catalog (topic, signal_key, signal_type, effective_since) VALUES (%s,%s,%s,%s)",
        ("pytest/T01/GENERATOR", "Gen_RPM_Max", "kpi", now),
    )
    seed_conn.commit()

    # "generator" is a SUFFIX of the topic, not a prefix -- list_signals(topic_prefix=...)
    # could never find this; search_signals must, since that's the whole point of this tool.
    result = search_signals(query="generator")
    assert any(r["signal_key"] == "Gen_RPM_Max" for r in result)
```

- [ ] **Step 6: Run to verify it fails**

Run: `pytest tests/test_server.py -k search_signals -v`
Expected: FAIL with `ImportError: cannot import name 'search_signals' from 'app.server'`

- [ ] **Step 7: Register the tool in `server.py`**

Add to `UNS_MCP/server/app/server.py`, after the existing `list_signals` tool definition:

```python
@mcp.tool()
def search_signals(query: str, limit: int = 10) -> list[dict]:
    """Find signals by NAME or KEYWORD -- unlike list_signals' topic_prefix
    (which only matches from the start of the asset-hierarchy path), this
    matches a substring anywhere in signal_key, description, or the full
    topic, case-insensitively. Use this whenever you're searching for a
    signal by what it's called rather than by a known asset path. Pass a
    few keywords (e.g. "generator rpm"), not a full sentence -- each word is
    matched independently and scored, so unrelated filler words dilute the
    ranking. Results are ordered by relevance, most likely match first."""
    conn = _connect()
    try:
        return db.search_signals(conn, query, limit)
    finally:
        conn.close()
```

- [ ] **Step 8: Run to verify it passes**

Run: `pytest tests/test_server.py -k search_signals -v`
Expected: PASS

- [ ] **Step 9: Run the full UNS_MCP test suite**

Run: `pytest -q` (from `UNS_MCP/server/`, with the same env vars as Step 2)
Expected: PASS, same count as before plus the 5 new tests, 0 regressions.

- [ ] **Step 10: Commit**

```bash
git add app/db.py app/server.py tests/test_db.py tests/test_server.py
git commit -m "feat(uns-mcp): add search_signals, a name/keyword search over the signal catalog"
```

---

### Task 2: Candidate-presentation protocol in `chat_agent.py`

**Files:**
- Modify: `UNS_DASHBOARD/backend/app/services/chat_agent.py`
- Test: `UNS_DASHBOARD/backend/tests/test_chat_agent.py`

**Interfaces:**
- Consumes: nothing new from other tasks (this task only needs `search_signals` to exist on the live MCP server for the eventual end-to-end test in Task 5 — its own unit tests use scripted providers exactly like every existing test in this file, never a live MCP call).
- Produces: `run_turn(...) -> tuple[str, list[dict], str | None, list[str], list[dict] | None]` — a 5th element, `candidates`, appended to the existing 4-tuple. `None` on every turn that never calls `present_signal_candidates`; otherwise the resolved candidate list. **This is a breaking change to `run_turn`'s return arity — Task 3 updates the one caller (`app/routers/chat.py`) in the same plan; until Task 3 lands, `chat.py` will fail to unpack the new tuple, which is expected and fine within this plan's own task sequence (each task's tests are self-contained; the full-repo consistency is restored by Task 3).**

- [ ] **Step 1: Write the failing tests**

Append to `UNS_DASHBOARD/backend/tests/test_chat_agent.py` (uses this file's existing `_ScriptedProvider`, `db` fixture, `ProviderResponse`/`ToolCall` imports — no new imports needed):

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `UNS_DASHBOARD/backend/`): `pytest tests/test_chat_agent.py -k present_signal_candidates -v`
Expected: FAIL — `run_turn()` returns a 4-tuple, so unpacking into 5 names raises `ValueError: not enough values to unpack`.

- [ ] **Step 3: Implement the protocol in `chat_agent.py`**

Add the new tool definition (near `_WRITE_TOOLS`, but kept in its own constant since it is not a write tool):

```python
_PRESENT_CANDIDATES_TOOL_NAME = "present_signal_candidates"

_PRESENT_CANDIDATES_TOOL = {
    "type": "function",
    "function": {
        "name": _PRESENT_CANDIDATES_TOOL_NAME,
        "description": (
            "Call this INSTEAD of guessing when search_signals returned 2+ plausible "
            "matches, or you are not confident which single one the user means. Do NOT "
            "call this for a single unambiguous match -- just use that signal directly. "
            "The candidates are shown to the user as clickable options; you do not need "
            "to also ask a follow-up question in your reply text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "signal_key": {"type": "string"},
                            "signal_type": {"type": "string"},
                            "unit": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["topic", "signal_key"],
                    },
                },
            },
            "required": ["candidates"],
        },
    },
}

_MAX_PRESENTED_CANDIDATES = 8
```

Change `run_turn`'s signature and body (the diff below shows every changed line; everything not shown is unchanged):

```python
async def run_turn(
    db: AsyncSession,
    provider: LLMProvider,
    history: list[dict],
    user_message: str,
    read_tools: list[dict] | None = None,
    current_dashboard_id: str | None = None,
) -> tuple[str, list[dict], str | None, list[str], list[dict] | None]:
    if read_tools is None:
        read_tools = await mcp_client.list_read_tools()
    tools = _WRITE_TOOLS + [_PRESENT_CANDIDATES_TOOL] + read_tools

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
            return response.text or "", new_messages, dashboard_id, actions, None

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
            if tc.name == _PRESENT_CANDIDATES_TOOL_NAME:
                candidates = tc.arguments.get("candidates") or []
                if not candidates:
                    result = {"error": "candidates must not be an empty list -- either present at least one, or answer directly without calling this tool"}
                    tool_message = {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)}
                    messages.append(tool_message)
                    new_messages.append(tool_message)
                    continue  # rejected -- let the model try again within this same turn

                candidates = candidates[:_MAX_PRESENTED_CANDIDATES]
                result = {"presented": True, "count": len(candidates)}
                tool_message = {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result, default=str)}
                messages.append(tool_message)
                new_messages.append(tool_message)
                reply_text = response.text or "Aquí tienes varias opciones, elige la que buscas:"
                assistant_reply_message = {"role": "assistant", "content": reply_text}
                new_messages.append(assistant_reply_message)
                return reply_text, new_messages, dashboard_id, actions, candidates

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
    return timeout_reply, new_messages, dashboard_id, actions, None
```

Notes on the change:
- `tools` now also includes `_PRESENT_CANDIDATES_TOOL` (a 3rd category alongside write tools and MCP read tools).
- The empty-candidates rejection uses `continue` (not `return`), so if the SAME response batch contains other tool calls after the rejected one, they still get processed normally, and the model gets another loop iteration to try again — matching the "loop continued" assertion in the test.
- A successful `present_signal_candidates` call returns immediately (`return reply_text, new_messages, dashboard_id, actions, candidates`), skipping any other tool calls that might be in the same batch (per the spec: "no further iterations, regardless of ... other tool calls in the same batch").
- Every other `return` statement in the function (final-text-reply, and the `_MAX_ITERATIONS` timeout) gains a trailing `, None` for the new 5th tuple element.

Also update the system prompt so the model knows both new tools exist and how they relate to `list_signals`/`search_signals`. Replace `_SYSTEM_PROMPT`'s current text (do not touch `_build_system_prompt`, which still appends the dashboard-context sentence unmodified):

```python
_SYSTEM_PROMPT = (
    "You are a helpful assistant that builds SCADA dashboards for an industrial monitoring system. "
    "Use list_signals to discover what signals exist under a KNOWN asset path before referencing "
    "one -- never guess a signal_key. "
    "IMPORTANT: list_signals' `topic_prefix` argument filters by MQTT TOPIC PATH -- the asset hierarchy, "
    "like 'site/line/machine' -- and NOT by signal name. Never pass a signal name, a signal_key, or a "
    "description as topic_prefix. "
    "If you are searching by NAME or KEYWORD instead of a known asset path (e.g. the user said "
    "'generator rpm' or 'motor speed'), use search_signals(query) instead of list_signals -- it "
    "matches signal_key/description/topic as substrings, case-insensitively, regardless of where in "
    "the path the word appears. Pass a few keywords, not a full sentence. "
    "If search_signals (or list_signals) returns 2+ plausible matches, or you are not confident which "
    "one the user means, call present_signal_candidates with those matches instead of guessing or "
    "asking a free-text clarifying question -- the user will pick one directly. Only call it with a "
    "non-empty list. Do not call it for a single unambiguous match; just use that signal directly. "
    "An empty result from either search tool only means nothing matched THAT query -- it never proves "
    "a named signal does not exist, so never tell the user a signal is missing on the strength of one "
    "narrow attempt; try search_signals with a broader or different keyword before giving up. "
    "Use get_current_value or get_historical_trend to check real data when useful. "
    "Use the write tools to create and edit the dashboard the user is describing. "
    "Always create a dashboard before adding charts to it if the conversation has not created one yet. "
    "Never call publish_dashboard unless the user explicitly asks to publish. "
    "Never claim you have created or modified anything unless a tool call actually returned a result -- "
    "if you intend to call a tool, emit a real tool call, never a description of one in your reply text. "
    "If the request is ambiguous in a way present_signal_candidates can't resolve (e.g. which dashboard, "
    "not which signal), ask a clarifying question in plain text instead of guessing."
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_agent.py -v`
Expected: PASS — the 4 new tests, plus every pre-existing test in this file still passing (they all call `run_turn` and unpack its return; check each pre-existing test's unpacking line already uses 4 names like `reply, new_messages, dashboard_id, actions = await chat_agent.run_turn(...)` — those will now fail to unpack a 5-tuple into 4 names).

**If any pre-existing test in this file fails to unpack**, update ONLY its unpacking line to add `, _` (ignoring the new candidates value, since none of those tests care about it), e.g. `reply, new_messages, dashboard_id, actions, _ = await chat_agent.run_turn(...)`. Do not change any other line of a pre-existing test.

- [ ] **Step 5: Commit**

```bash
git add app/services/chat_agent.py tests/test_chat_agent.py
git commit -m "feat(uns-dashboard): add present_signal_candidates protocol to the tool-calling loop"
```

---

### Task 3: Wire candidates through the HTTP router and schemas

**Files:**
- Modify: `UNS_DASHBOARD/backend/app/schemas/chat.py`
- Modify: `UNS_DASHBOARD/backend/app/routers/chat.py`
- Test: `UNS_DASHBOARD/backend/tests/test_chat_router.py`

**Interfaces:**
- Consumes: `run_turn(...) -> tuple[str, list[dict], str | None, list[str], list[dict] | None]` (Task 2).
- Produces: `ChatMessageResponse.candidates: list[SignalCandidate] | None`.

- [ ] **Step 1: Write the failing test**

Append to `UNS_DASHBOARD/backend/tests/test_chat_router.py`. This needs a scripted/mocked provider the same way `test_list_sessions_shows_a_session_with_its_first_user_message` already does in this file (check that test for the exact `monkeypatch` pattern on `chat_router._build_provider`/`mcp_client.list_read_tools` and reuse it verbatim, only changing the fake provider's returned response):

This file already defines a module-level `_async_empty_list()` helper (used by
`test_list_sessions_shows_a_session_with_its_first_user_message`) — reuse it, do not
redefine it. Match that same test's exact import/monkeypatch style:

```python
def test_send_message_surfaces_candidates_in_the_response(client: TestClient, monkeypatch):
    from app.routers import chat as chat_router
    from app.services import mcp_client
    from app.services.llm_providers.base import ProviderResponse, ToolCall

    class _FakeProvider:
        async def send(self, messages, tools):
            return ProviderResponse(
                text=None,
                tool_calls=[ToolCall(
                    id="1", name="present_signal_candidates",
                    arguments={"candidates": [
                        {"topic": "GALERNA/T01/GENERATOR", "signal_key": "Gen_RPM_Max", "signal_type": "kpi", "unit": "rpm", "description": None},
                    ]},
                )],
            )

    monkeypatch.setattr(chat_router, "_build_provider", lambda: _FakeProvider())
    monkeypatch.setattr(mcp_client, "list_read_tools", lambda: _async_empty_list())

    created = client.post("/chat/sessions").json()
    response = client.post(f"/chat/sessions/{created['id']}/messages", json={"message": "busca el rpm del generador"})

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == [
        {"topic": "GALERNA/T01/GENERATOR", "signal_key": "Gen_RPM_Max", "signal_type": "kpi", "unit": "rpm", "description": None},
    ]
```

- [ ] **Step 2: Run to verify it fails**

Run (from `UNS_DASHBOARD/backend/`, with `DATABASE_URL` pointing at the isolated test database per `tests/README.md`): `pytest tests/test_chat_router.py -k candidates -v`
Expected: FAIL — `ChatMessageResponse` has no `candidates` field yet (Pydantic validation error or `KeyError` on `body["candidates"]`), and/or `send_message` fails to unpack `run_turn`'s new 5-tuple.

- [ ] **Step 3: Add the schema**

In `UNS_DASHBOARD/backend/app/schemas/chat.py`, add (near `ChatMessageResponse`):

```python
class SignalCandidate(BaseModel):
    topic: str
    signal_key: str
    signal_type: str | None = None
    unit: str | None = None
    description: str | None = None
```

Change `ChatMessageResponse` to:

```python
class ChatMessageResponse(BaseModel):
    reply: str
    dashboard_id: str | None
    actions: list[str]
    candidates: list[SignalCandidate] | None = None
```

- [ ] **Step 4: Update the router**

In `UNS_DASHBOARD/backend/app/routers/chat.py`:

Add `SignalCandidate` to the existing `from app.schemas.chat import (...)` block.

Update `send_message`'s call to `run_turn` and its final `return` (every other line of this function is unchanged):

```python
            reply, new_messages, dashboard_id, actions, candidates = await chat_agent.run_turn(
                db, provider, history, body.message, current_dashboard_id=session.dashboard_id
            )
```

```python
    return ChatMessageResponse(reply=reply, dashboard_id=session.dashboard_id, actions=actions, candidates=candidates)
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/test_chat_router.py -v`
Expected: PASS — the new test, plus every pre-existing test in this file (none of them assert on `candidates`, so Pydantic's default of `None` satisfies them unchanged).

- [ ] **Step 6: Run the full backend suite**

Run: `pytest -q` (from `UNS_DASHBOARD/backend/`, isolated test databases per `tests/README.md`)
Expected: PASS, 0 regressions.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/chat.py app/routers/chat.py tests/test_chat_router.py
git commit -m "feat(uns-dashboard): surface signal candidates through the chat HTTP response"
```

---

### Task 4: Frontend — candidate buttons in `ChatPanel`

**Files:**
- Modify: `UNS_DASHBOARD/frontend/src/types/dashboard.ts`
- Modify: `UNS_DASHBOARD/frontend/src/components/editor/ChatPanel.tsx`
- Test: `UNS_DASHBOARD/frontend/src/components/editor/__tests__/ChatPanel.test.tsx`

**Interfaces:**
- Consumes: `ChatMessageResult.candidates: SignalCandidate[] | null` (Task 3's shape, already returned by the existing `api.chat.sendMessage` call — no `api/client.ts` change needed, since `ChatMessageResult`'s type just needs the new field and axios already passes the whole JSON body through).

- [ ] **Step 1: Add the type**

In `UNS_DASHBOARD/frontend/src/types/dashboard.ts`, add (near `ChatMessageResult`):

```typescript
export interface SignalCandidate {
  topic: string;
  signal_key: string;
  signal_type: string | null;
  unit: string | null;
  description: string | null;
}
```

Change `ChatMessageResult` to:

```typescript
export interface ChatMessageResult {
  reply: string;
  dashboard_id: string | null;
  actions: string[];
  candidates: SignalCandidate[] | null;
}
```

Also change `ChatMessage` (the LOCAL rendering type `ChatPanel` uses for its own message list — distinct from the backend's stored envelope) to optionally carry candidates on the message it belongs to:

```typescript
export interface ChatMessage {
  role: string;
  content: Record<string, unknown>;
  candidates?: SignalCandidate[] | null;
}
```

- [ ] **Step 2: Write the failing test**

Append to `UNS_DASHBOARD/frontend/src/components/editor/__tests__/ChatPanel.test.tsx` (match this file's existing `vi.mock` setup for `../../../api/client` — check its current mocked shape for `api.chat.status`/`createSession`/`sendMessage` before adding to it, since this test needs `sendMessage` to resolve with a `candidates` array):

```tsx
test("renders signal candidates as clickable buttons and sends the picked one", async () => {
  const user = userEvent.setup();
  vi.mocked(api.chat.status).mockResolvedValue({ available: true, provider_type: "openai_compatible", reason: null });
  vi.mocked(api.chat.createSession).mockResolvedValue({ id: "session-1" });
  vi.mocked(api.chat.sendMessage).mockResolvedValueOnce({
    reply: "Encontré varias señales parecidas:",
    dashboard_id: null,
    actions: [],
    candidates: [
      { topic: "GALERNA/T01/GENERATOR", signal_key: "Gen_RPM_Max", signal_type: "kpi", unit: "rpm", description: null },
      { topic: "GALERNA/T01/GENERATOR/_informative", signal_key: "Gen_RPM_Max_Raw", signal_type: "raw", unit: "rpm", description: null },
    ],
  });

  render(<ChatPanel onDashboardCreated={vi.fn()} />);

  const input = await screen.findByPlaceholderText("Describe el dashboard que quieres…");
  await user.type(input, "busca el rpm del generador");
  await user.click(screen.getByText("Enviar"));

  const candidateButton = await screen.findByText(/Gen_RPM_Max\b/);
  expect(candidateButton).toBeInTheDocument();
  expect(screen.getByText(/Gen_RPM_Max_Raw/)).toBeInTheDocument();

  vi.mocked(api.chat.sendMessage).mockResolvedValueOnce({
    reply: "Perfecto, usaré esa.",
    dashboard_id: null,
    actions: [],
    candidates: null,
  });

  await user.click(candidateButton);

  expect(api.chat.sendMessage).toHaveBeenLastCalledWith(
    "session-1",
    expect.stringContaining("Gen_RPM_Max")
  );
  expect(api.chat.sendMessage).toHaveBeenLastCalledWith(
    "session-1",
    expect.stringContaining("GALERNA/T01/GENERATOR")
  );
});
```

(Match this file's existing imports for `render`/`screen`/`userEvent`/`vi` — check the top of the current test file rather than assuming; add any that are missing.)

- [ ] **Step 3: Run to verify it fails**

Run (from `UNS_DASHBOARD/frontend/`): `npm run test -- --run ChatPanel`
Expected: FAIL — no candidate buttons are rendered yet.

- [ ] **Step 4: Implement candidate rendering + click-to-send in `ChatPanel.tsx`**

Change the `send` function to accept an optional override text (so a candidate click can send specific text without going through the `input` state box), and store `candidates` on the pushed assistant message:

```typescript
  const send = async (overrideText?: string) => {
    const userText = overrideText ?? input;
    if (!sessionId || !userText.trim() || sending) return;
    if (overrideText === undefined) setInput("");
    setSending(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: { text: userText } }]);
    try {
      const result = await api.chat.sendMessage(sessionId, userText);
      setMessages((m) => [...m, { role: "assistant", content: { text: result.reply }, candidates: result.candidates ?? null }]);
      if (result.dashboard_id && result.dashboard_id !== reportedDashboardIdRef.current) {
        reportedDashboardIdRef.current = result.dashboard_id;
        onDashboardCreated(result.dashboard_id);
      } else if (result.actions.length > 0) {
        onDashboardChanged?.();
      }
    } catch {
      setError("El asistente no respondió. Inténtalo de nuevo.");
    } finally {
      setSending(false);
    }
  };

  const pickCandidate = (c: SignalCandidate) => {
    send(`Usa la señal ${c.signal_key} en ${c.topic}`);
  };
```

Add `SignalCandidate` to the existing `import type { ChatMessage } from "../../types/dashboard";` line (`import type { ChatMessage, SignalCandidate } from "../../types/dashboard";`).

Change the message-rendering block to also render candidate buttons under a message that has them:

```tsx
        {messages.map((m, i) => (
          <div key={i} className="flex flex-col gap-1">
            <div className={`text-sm rounded-lg px-3 py-2 max-w-[85%] ${m.role === "user" ? "self-end bg-brand text-white" : "self-start bg-surface"}`}>
              {String(m.content.text ?? "")}
            </div>
            {m.candidates && m.candidates.length > 0 && (
              <div className="flex flex-wrap gap-1 self-start max-w-[85%]">
                {m.candidates.map((c, ci) => (
                  <button
                    key={ci}
                    onClick={() => pickCandidate(c)}
                    disabled={sending}
                    className="text-xs px-2 py-1 rounded-full border border-border bg-surface hover:bg-surface-subtle disabled:opacity-50"
                  >
                    {c.signal_key} — {c.topic}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
```

Change the send button's `onClick` from `onClick={send}` to `onClick={() => send()}` (since `send` now takes an optional argument, and a raw DOM click event must not be passed as `overrideText`).

- [ ] **Step 5: Run to verify it passes**

Run: `npm run test -- --run ChatPanel`
Expected: PASS (all `ChatPanel.test.tsx` tests, including the new one).

- [ ] **Step 6: Run the full frontend suite and build**

Run: `npm run test -- --run` then `npm run build`
Expected: PASS / clean build, 0 regressions.

- [ ] **Step 7: Commit**

```bash
git add src/types/dashboard.ts src/components/editor/ChatPanel.tsx src/components/editor/__tests__/ChatPanel.test.tsx
git commit -m "feat(uns-dashboard): render signal candidates as one-click buttons in the chat panel"
```

---

### Task 5: Wiring and end-to-end verification

**Files:** none (verification only — every file this feature needs was already modified in Tasks 1-4).

- [ ] **Step 1: Rebuild the real UNS_MCP and dashboard_backend containers**

```bash
cd UNS_MCP && docker compose up -d --build mcp_server
cd ../UNS_DASHBOARD && docker compose up -d --build dashboard_backend
```

- [ ] **Step 2: Confirm `search_signals` is now a discoverable MCP tool**

```bash
curl -s http://localhost:8001/chat/status
```
Expected: `{"available":true,...}` (unchanged from before — this only confirms the stack is up).

- [ ] **Step 3: Live conversation test — the exact scenario that motivated this plan**

Start a session bound to no dashboard, and ask for a signal using a word that is NOT a topic prefix (mirroring the real failure this plan fixes):
```bash
SESSION=$(curl -s -X POST http://localhost:8001/chat/sessions | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST http://localhost:8001/chat/sessions/$SESSION/messages \
  -H "Content-Type: application/json" \
  -d '{"message": "busca las senales de rpm del generador"}'
```
Read the actual reply and `candidates` field, don't just check the HTTP status:
- If exactly one clear match exists in the live catalog, the model should proceed directly (no `candidates`, a real answer or a chart-adding flow if asked).
- If 2+ plausible matches exist, `candidates` should be a non-empty list and the reply should NOT be a confident false "doesn't exist" claim (the original bug this plan targets).
- If genuinely nothing matches, the model should say so plainly (also acceptable) — but confirm via direct SQL against `uns_silver_postgres`'s `signal_catalog` that nothing SHOULD have matched, the same way Task 9 of the original chat-agent plan verified this.

- [ ] **Step 4: Frontend click-through**

Open `http://localhost:3002`, open a dashboard's editor, ask the chat the same ambiguous question. If `candidates` came back non-empty, confirm the buttons render and clicking one sends the expected canned message and the model proceeds correctly with the now-unambiguous signal.

- [ ] **Step 5: Commit** (only if Steps 1-4 required any fix; otherwise this task has nothing to commit)

```bash
git add -A
git commit -m "chore(uns-dashboard): verify signal search + candidate disambiguation end-to-end"
```
