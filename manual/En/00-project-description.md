# Project Description: INARI_V05

## In one sentence

INARI_V05 connects the machines on an industrial plant floor with the people who need to understand them — it captures what machines are saying (sensor readings, alarms, states), stores it in an orderly way, and lets anyone — from an operator to an engineer — query it, visualize it, or simply ask an AI assistant for it in plain language.

## For a non-technical reader

Picture a plant with dozens of machines: motors, generators, temperature/pressure/vibration sensors. Each one is constantly "talking" — reporting its state, its speed, whether something is wrong. The usual problem on a plant floor is that this information is scattered: every machine in its own system, its own format, hard to bring together and hard to query.

INARI_V05 solves this in four steps:

1. **Listens** — everything machines say arrives on one central channel (like a radio frequency every machine tunes into), so nothing gets lost and everything ends up in one place.
2. **Stores** — that stream of messages is archived in an orderly way, like a history you can go back to months later to see exactly what happened on a given day.
3. **Cleans and translates** — raw data (loose numbers, technical codes) gets turned into something meaningful: not just "the value is 1450", but "Generator T01's average speed is 1450 RPM", with units, a description, and a version history of how its definition changed over time.
4. **Lets you ask** — on top of that clean data you can build visual dashboards (live and historical charts), and, most recently, you can simply *ask* an AI assistant: "create a chart with the generator's speed" — the assistant finds the right signal, adds it to the dashboard, and if it isn't sure which one you mean, it offers you clickable options instead of guessing.

The whole system runs on the plant's own network (nothing goes out to the internet unless explicitly configured), organized into independent pieces that can be stopped, upgraded, or replaced one at a time without bringing down the rest.

## Architecture for a technical reader

The system is organized into **six independent modules**, each with its own `docker-compose.yml`, that can start standalone or all together (the root `docker-compose.yml` simply includes all six under one shared network, `uns_manager_net`). Each module is a folder named after itself (`UNS_MANAGER`, `UNS_HISTORIAN`, etc.).

```
                    ┌──────────────┐
   Sensors/PLCs  →  │  UNS_MANAGER │ → MQTT (EMQX) + Node-RED
                    └──────┬───────┘
                           │ raw MQTT messages ("bronze")
                           ▼
                    ┌──────────────┐
                    │ UNS_HISTORIAN│  full, unfiltered history
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  UNS_SILVER  │  normalizes: signal catalog,
                    └──────┬───────┘  typed readings, alarm/event log
                           │
                           ▼
                    ┌──────────────┐
                    │   UNS_MCP    │  read-only API over the above
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐      ┌────────────┐
                    │ UNS_DASHBOARD│ ───→ │ UNS_OLLAMA │ (local LLM)
                    │ (dashboards+ │      └────────────┘
                    │    chat)     │
                    └──────────────┘
```

| Module | What it does | Tech stack | Ports (host) |
|---|---|---|---|
| **UNS_MANAGER** | Entry point: receives machines' MQTT messages, lets you build automation flows (Node-RED), and exposes its own API/panel | EMQX (MQTT broker), Node-RED, FastAPI, React, Postgres | Postgres 5433, MQTT 1883, EMQX dashboard 18083, API 8000, frontend 3001, Node-RED 1880 |
| **UNS_HISTORIAN** | Archives **every** MQTT message exactly as it arrives, unfiltered — the raw ("bronze") history | TimescaleDB (Postgres + time-series), pgAdmin, a dedicated MQTT ingestor | Postgres 5434, pgAdmin 5051 |
| **UNS_SILVER** | Turns that raw history into meaningful data: a versioned signal catalog (name, unit, thresholds), typed readings, an event/alarm log | TimescaleDB, pgAdmin, a bronze-to-silver normalizer | Postgres 5436 |
| **UNS_MCP** | Exposes the above over HTTP, read-only, via the Model Context Protocol (MCP) — built so an LLM/agent can query it as just another tool | Python MCP server | 8095 |
| **UNS_DASHBOARD** | The visual dashboards (live and historical charts) and, the newest piece, an **AI chat** that creates and edits those dashboards from natural language | FastAPI + async SQLAlchemy, React + Vite + TypeScript, Postgres, Redis (an MQTT→Redis bridge for low-latency live data) | Postgres 5435, backend 8001, frontend 3002 |
| **UNS_OLLAMA** | A language model (LLM) running locally, on the plant's own machine/network — no data leaves the premises | Ollama, GPU-accelerated where available | 11434 |

### The AI chat, in more detail

This is the most recently built piece. It lives inside `UNS_DASHBOARD` and works like this:

- The user types something like *"add a chart with the generator's RPM"* into a chat panel inside a dashboard's editor.
- The system sends that message to the language model (`UNS_OLLAMA`, running locally), along with a set of **tools** the model can use: reading real data (through `UNS_MCP`, read-only) and writing changes to the dashboard (create/edit/delete a chart, publish — always on drafts, never on an already-published dashboard).
- If the model isn't confident which signal is the right one, it doesn't guess — it can offer several candidates as clickable buttons so the user picks with one click.
- Designed to swap LLM providers in the future (local via Ollama, or an external one like OpenAI/Claude/OpenRouter) without a redesign — today only Ollama is actually implemented.
- If no provider is configured or reachable, the chat simply disables itself (no text box appears) — it never errors, never breaks the rest of the panel.

## Seeing it run

With Docker and Docker Compose installed, from the repository root:

```bash
docker compose up -d
```

This brings up all six modules together. Each one can also start standalone from its own folder (`cd UNS_DASHBOARD && docker compose up -d`, etc.) to work on one without touching the rest.

`manual/En/` (this same folder) has step-by-step guides for verifying specific parts of the system — e.g. `01-verify-historian-data-pgadmin.md` to confirm the history is actually being saved, or `02-verify-chat-agent-dashboard.md` to test the chat end to end.

## Where the technical documentation lives

- **Design specs** (architecture, decisions): `<module>/docs/superpowers/specs/`
- **Implementation plans** (task by task): `<module>/docs/superpowers/plans/`
- **Repository development rules**: `AGENTS.md`, at the repo root

Each module keeps its own documentation under its own folder — there is no centralized `documents/` or `Plan/` directory like in very early drafts of the project; each piece of documentation lives next to the code it describes.
