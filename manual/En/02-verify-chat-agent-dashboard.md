# Tutorial: verify the dashboard-building chat (UNS_DASHBOARD + UNS_OLLAMA + UNS_MCP)

This verifies the piece just merged to `master`: a chat panel inside UNS_DASHBOARD that creates/edits draft dashboards from natural-language requests, backed by a local LLM (Ollama) that queries real UNS_SILVER data through UNS_MCP.

## 0. Check everything is up

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "ollama|mcp|dashboard|silver"
```

You should see, all `Up` (ideally `healthy`):

- `uns_ollama`
- `uns_mcp_server`
- `uns_dashboard_backend`, `uns_dashboard_frontend`, `uns_dashboard_postgres`
- `uns_silver_postgres` (where the real signals come from)

If `uns_ollama` doesn't exist yet, bring it up:

```bash
cd UNS_OLLAMA && docker compose up -d
```

## 1. Check the assistant's status via API

```bash
curl -s http://localhost:8001/chat/status
```

Expected result:

```json
{"available":true,"provider_type":"openai_compatible","reason":null}
```

If it says `"available":false`, check the `reason` field — usually Ollama hasn't pulled the model yet, or `MCP_API_KEY`/`LLM_PROVIDER_TYPE` aren't set in `UNS_DASHBOARD/.env`. To make it permanent (not just on the already-running container), add to `UNS_DASHBOARD/.env`:

```
LLM_PROVIDER_TYPE=openai_compatible
MCP_API_KEY=changeme-local-dev-key
```

(the key must match `MCP_API_KEY` in `UNS_MCP/.env`) and rebuild:

```bash
cd UNS_DASHBOARD && docker compose up -d --build dashboard_backend
```

## 2. Try it from the browser (the real way to check it)

1. Open `http://localhost:3002`
2. Go into a dashboard's editor (create a new one or open a draft)
3. Look for the chat panel in the editor. If the assistant is available you'll see an enabled text box; if not, you'll see "Asistente no disponible — …" (Spanish UI copy) and **no text box or send button at all** (this is intentional: with no provider configured, the chat disables itself, it never errors)
4. Type something like:

   > Create a dashboard called Manual Test and add a chart with any signal that exists

5. Wait for the reply (may take a few seconds, the model runs locally). It should tell you what it did, and if it created a new dashboard the page should navigate you to its editor

## 3. Confirm it via API (the "hard proof" version)

```bash
curl -s http://localhost:8001/dashboards/ | python -c "import sys,json; [print(d['id'], d['name'], d['status']) for d in json.load(sys.stdin)]"
```

Find the dashboard you just named. Grab its `id` and check its detail:

```bash
curl -s http://localhost:8001/dashboards/<the-id-above>
```

You should see `"status":"draft"` and, if the chat found a real signal, a `charts` array with at least one entry.

## 4. Check it respects the rules

- Ask it to **publish** the dashboard, then ask it to add another chart or delete one → it should refuse, explaining it's already published (the chat only edits drafts)
- Notice it never offers "delete the whole dashboard" — that capability doesn't exist in the chat on purpose, only deleting individual charts

## 5. Check graceful degradation (turn off the LLM, confirm nothing breaks)

```bash
cd UNS_OLLAMA && docker compose stop
curl -s http://localhost:8001/chat/status
```

Expected: `{"available":false,...}` with a reason. Reload the editor in the browser: the chat should show as unavailable, not broken. Then bring it back:

```bash
cd UNS_OLLAMA && docker compose start
```

## 6. See the stored conversations (pgAdmin)

In pgAdmin (`http://localhost:5051`, or UNS_DASHBOARD's own pgAdmin if it has one — otherwise connect any Postgres client to `localhost:5435`, credentials in `UNS_DASHBOARD/.env`):

```
Databases → uns_dashboard → Schemas → public → Tables → chat_sessions / chat_messages
```

```sql
SELECT id, dashboard_id, created_at FROM chat_sessions ORDER BY created_at DESC LIMIT 5;

SELECT role, content, created_at
FROM chat_messages
WHERE session_id = '<the session id above>'
ORDER BY created_at;
```

You should see the full conversation: your messages (`role='user'`), the replies (`role='assistant'`), and, if the model called any tool, `role='tool'` rows with each call's result.

## 7. If something looks off

```bash
docker logs uns_dashboard_backend --tail 50
docker logs uns_ollama --tail 30
docker logs uns_mcp_server --tail 30
```

One known failure mode: the model confuses a signal's name with a tool's "topic prefix" filter and tells you a signal doesn't exist when it actually does — a known quirk of `qwen2.5:14b-instruct`, already mitigated in the system prompt, but it can still happen occasionally. That's the LLM being wrong, not the system being broken.
