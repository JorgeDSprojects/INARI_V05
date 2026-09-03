# UNS Dashboard

Real-time SCADA dashboard authoring and viewing. See
`docs/superpowers/specs/2026-09-03-uns-dashboard-design.md` for the full design.

## Running standalone

Requires `UNS_MANAGER` (for EMQX) and `UNS_HISTORIAN` (for history/signal catalog) already running:

```bash
cd UNS_MANAGER && docker compose up -d
cd ../UNS_HISTORIAN && docker compose up -d
cd ../UNS_DASHBOARD && cp .env.example .env && ./scripts/up.sh
```

- Backend: http://localhost:8001 (docs at `/docs`)
- Frontend: http://localhost:3002

## End-to-end smoke test

1. `docker compose up -d` from the repo root (brings up all three stacks together).
2. Open the frontend, create a dashboard, add a `live` gauge chart bound to an
   existing `_informative` signal (use the signal picker's "buscar" button —
   it lists topics already captured by `UNS_HISTORIAN`).
3. Publish the dashboard and open its viewer URL.
4. Publish a synthetic reading: `mosquitto_pub -h localhost -p 1883 -t '<topic>' -m '{"<signal_key>": 42}'`.
5. Confirm the gauge updates within ~1s — this exercises the full
   `EMQX → bridge → Redis Stream → backend WebSocket → browser` path.
6. Add a `historical` `relative: 24h` timeseries chart on the same signal,
   confirm it renders points from `UNS_HISTORIAN` (seeded by step 4 and any
   prior traffic on that topic).
