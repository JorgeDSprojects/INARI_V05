# UNS Manager — Features A2–A9 Design Spec
**Date:** 2026-09-01  
**Status:** Approved  
**Scope:** 7 new features aligned to the uns_manage.pen mockup screens

---

## Context

The UNS Manager app already has a working core (ISA-95 tree CRUD, Asset _descriptive editor, EMQX publish). This spec covers the 7 gaps identified in the mockup review. Implementation follows Option 1: incremental by dependency order.

**Dependency order:** A7 → A8 → A5 → A6 → A2 → A3 → A9

---

## Key Decisions (from clarifying questions)

| Decision | Choice |
|---|---|
| Broker topology | Single EMQX broker (configurable via UI) |
| Node Types | JSON Schema templates that validate `_descriptive` payload |
| Data Branch discovery | Automatic via EMQX HTTP Management API (no DB table) |
| Copy/Move publish | Two-step: move first, then user decides when to publish |

---

## Section 1 — Data Models

### New table: `brokers`

```sql
CREATE TABLE brokers (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label       VARCHAR(255) NOT NULL,
  host        VARCHAR(255) NOT NULL,
  port        INT NOT NULL DEFAULT 1883,
  api_port    INT NOT NULL DEFAULT 18083,
  username    VARCHAR(255),
  password    VARCHAR(255),
  use_tls     BOOL NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`status` is not persisted — computed at runtime via `GET /api/v5/status` on the EMQX HTTP API.

### New table: `node_types`

```sql
CREATE TABLE node_types (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        VARCHAR(255) NOT NULL UNIQUE,
  description TEXT,
  json_schema JSONB NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`json_schema` holds a JSON Schema draft-7 document. Validation uses Python's `jsonschema` library.

### Modified table: `assets`

```sql
ALTER TABLE assets
  ADD COLUMN node_type_id UUID REFERENCES node_types(id) ON DELETE SET NULL;
```

When `node_type_id` is set, `POST`/`PUT` on an asset validates `descriptive_payload` against the node type's `json_schema` before saving. Validation failure returns HTTP 422 with schema errors.

### Data Branches — no table

Active subscribers are discovered on-demand via:
```
GET http://{broker.host}:{broker.api_port}/api/v5/subscriptions?topic={uns_topic}
```
Response is proxied directly to the frontend. If EMQX is unreachable, returns `[]` with header `X-Branch-Source: unavailable`. No caching, no DB persistence.

---

## Section 2 — Backend API

All routes under `/api/v1/`. New routers registered in `backend/app/main.py`.

### A7 — `/brokers`

```
GET    /brokers/                   → list[BrokerRead]
POST   /brokers/                   → BrokerRead          body: BrokerCreate
GET    /brokers/{id}               → BrokerRead
PUT    /brokers/{id}               → BrokerRead          body: BrokerUpdate
DELETE /brokers/{id}               → 204

GET    /brokers/{id}/status        → BrokerStatus        calls EMQX /api/v5/status
POST   /brokers/{id}/test          → BrokerTestResult    opens paho connection, measures latency
```

`BrokerStatus`: `{ connected: bool, version: str, node: str }`  
`BrokerTestResult`: `{ ok: bool, latency_ms: int | null, error: str | null }`

**Implementation:** `backend/app/routers/brokers.py` + `backend/app/services/broker_service.py`  
Service uses `httpx.AsyncClient` for EMQX HTTP API calls and `paho.mqtt.client` for connection test.

### A8 — `/node-types`

```
GET    /node-types/                → list[NodeTypeRead]
POST   /node-types/                → NodeTypeRead        body: NodeTypeCreate
GET    /node-types/{id}            → NodeTypeRead
PUT    /node-types/{id}            → NodeTypeRead        body: NodeTypeUpdate
DELETE /node-types/{id}            → 204

POST   /node-types/{id}/validate   → ValidationResult   body: { payload: object }
```

`ValidationResult`: `{ valid: bool, errors: list[str] }`  
Uses `jsonschema.validate()` with `jsonschema.exceptions.ValidationError` to collect error messages.

**Implementation:** `backend/app/routers/node_types.py` + `backend/app/services/node_type_service.py`  
Add `jsonschema==4.23.0` to `requirements.txt`.

### A3 — `/tree` extensions

```
POST   /tree/copy                  → SubtreeCopyResult
POST   /tree/move                  → SubtreeMoveResult
POST   /tree/publish-subtree       → SubtreePublishResult
```

**Bodies:**
```python
# copy / move
{
  "source_id": str,
  "source_level": Literal["enterprise","site","area","line","cell","asset"],
  "target_parent_id": str,
  "target_level": Literal["enterprise","site","area","line","cell"]  # one level above source
}
```

**Copy:** recursively duplicates nodes with new UUIDs, preserving `descriptive_payload` and `node_type_id`. All inserts in a single transaction.  
**Move:** updates the FK of the root node only (`site.enterprise_id`, `area.site_id`, etc.), single transaction.  
**publish-subtree:** walks the subtree, calls `publish_descriptive()` for each Asset that has `descriptive_payload`. Returns counts of `published` and `failed`.

**Implementation:** `backend/app/routers/tree.py` (extend existing) + `backend/app/services/subtree_service.py`

### A2 — Data branches endpoint

```
GET    /cells/{cell_id}/assets/{asset_id}/branches
       → list[DataBranch]
```

`DataBranch`: `{ client_id: str, topic_filter: str, qos: int, connected_at: str | null }`

Fetches from EMQX `GET /api/v5/subscriptions?topic={uns_topic}`. If broker not configured or unreachable, returns `[]`. No auth required for EMQX Community Edition; uses `broker.username`/`password` as Basic auth for Enterprise.

**Implementation:** `backend/app/routers/assets.py` (extend existing)

### A9 — Sync status endpoint

```
GET    /cells/{cell_id}/assets/{asset_id}/sync-status
       → SyncStatus
```

`SyncStatus`:
```python
{
  synced: bool,
  db_payload: dict | None,
  emqx_payload: dict | None,   # from retained message
  diff: list[str]              # list of keys that differ
}
```

Fetches retained message from EMQX `GET /api/v5/mqtt/topic/{url_encoded_topic}`. Compares with `asset.descriptive_payload`. Diff is computed as symmetric difference of top-level keys plus changed values.

**Implementation:** `backend/app/routers/assets.py` (extend existing) + logic in `broker_service.py`

---

## Section 3 — Frontend Architecture

### File structure changes

```
frontend/src/
  components/
    # New pages
    BrokersView.tsx
    NodeTypesView.tsx
    
    # New modals
    CopyMoveModal.tsx
    CreateWithDescriptiveModal.tsx
    CreateUnsWizard.tsx
    
    # Modified
    NodeWorkspace.tsx     (branches tab + sync status banner)
    TreePanel.tsx         (copy/move hover actions on nodes)
    AppHeader.tsx         (already has nav tabs for brokers/nodetypes)
    App.tsx               (wire new views to AppView state)
  
  api/
    client.ts             (add broker, nodeType, branch, syncStatus, tree copy/move endpoints)
  
  types/
    uns.ts                (add Broker, NodeType, DataBranch, SyncStatus interfaces)
```

### `BrokersView`

- Full-width table: label, host:port, api_port, TLS badge, status badge (● green / ● red)
- Status refreshes every 30 seconds via `useEffect` + `setInterval`
- "Register broker" button → inline form (label, host, port, api_port, username, password, TLS toggle)
- Row click → right panel: full details + "Test connection" button
- Test result: shows latency badge or error message inline

### `NodeTypesView`

- Table: name, description, preview of required fields from `json_schema`
- "New node type" → modal with: name field, description field, `JsonEditorPanel` for the JSON Schema (full height, edit mode)
- Row click → right panel: full schema editor, editable in-place with Save button
- Validates that the JSON Schema itself is valid JSON before saving

### `NodeWorkspace` — branches tab (A2)

- On tab focus: calls `GET /cells/{cell_id}/assets/{id}/branches`
- Shows table: client_id, topic_filter, QoS, connected_at
- Tab label updates to `Data branches · N` with real count
- Empty state: "No active subscribers found"
- EMQX unreachable state: warning banner "Branch discovery unavailable — EMQX unreachable"
- Refresh button to re-query on demand

### `NodeWorkspace` — sync status (A9)

- On asset load: calls `GET /cells/{cell_id}/assets/{id}/sync-status`
- `synced: true` → green SYNCED badge (existing behavior)
- `synced: false` → red UNSYNCED badge + collapsible red banner below header:
  - Shows diff: keys only in DB, keys only in EMQX, changed values
  - "Re-sync" button → calls publish endpoint + re-fetches sync status

### `CopyMoveModal` (A3)

- Triggered from hover action on tree node (copy icon / move icon)
- Left panel: source node info (read-only)
- Right panel: destination selector
  - Dropdown: target level (must be valid parent of source level)
  - Tree picker: filtered list of nodes at target level
- Preview section: list of new MQTT topics that will be generated (computed client-side)
- Confirm button → POST `/tree/copy` or `/tree/move`
- On success: dialog "Subtree copied/moved. Publish to EMQX now?"
  - "Publish" → POST `/tree/publish-subtree` + shows count
  - "Later" → closes modal

### `CreateUnsWizard` (A5)

3-step stepper modal triggered from "New namespace" button in CatalogView:

1. **Name** — Enterprise name (text input) + description (optional)
2. **Broker** — displays configured broker (host:port, status badge). Read-only. Message if no broker configured.
3. **Confirm** — preview of root MQTT topic + "Create Enterprise" button

### `CreateWithDescriptiveModal` (A6)

Enhanced "Add child" for Asset level in TreePanel:
- Form fields: name (required), description (optional)
- Node type dropdown (loads from `GET /node-types/`) — optional
- If node type selected: loads its `json_schema` as template payload in editor
- `JsonEditorPanel` inline (fixed height 200px, edit mode)
- Validates payload against selected node type before enabling Save
- On save: `POST /cells/{cell_id}/assets/` with `descriptive_payload` included

---

## Implementation Plan (dependency order)

| Step | Feature | New files | Modified files |
|------|---------|-----------|----------------|
| 1 | A7 Broker Registry | `models/broker.py`, `schemas/broker.py`, `routers/brokers.py`, `services/broker_service.py`, migration | `main.py`, `client.ts`, `types/uns.ts`, `App.tsx` |
| 2 | A8 Node Type Catalog | `models/node_type.py`, `schemas/node_type.py`, `routers/node_types.py`, `services/node_type_service.py`, migration | `main.py`, `models/uns.py` (add FK), `client.ts`, `types/uns.ts`, `App.tsx` |
| 3 | A5 Create UNS Wizard | `components/CreateUnsWizard.tsx` | `components/CatalogView.tsx` |
| 4 | A6 Create With Descriptive | `components/CreateWithDescriptiveModal.tsx` | `components/TreePanel.tsx` |
| 5 | A2 Data Branches | extend `routers/assets.py`, extend `services/broker_service.py` | `components/NodeWorkspace.tsx`, `client.ts` |
| 6 | A3 Copy/Move Subtree | `services/subtree_service.py`, `components/CopyMoveModal.tsx` | `routers/tree.py`, `components/TreePanel.tsx`, `client.ts` |
| 7 | A9 Sync Failure | extend `routers/assets.py` | `components/NodeWorkspace.tsx`, `client.ts` |

---

## Dependencies added

- `jsonschema==4.23.0` → `backend/requirements.txt`
- `httpx` already present (used for EMQX HTTP API calls)
- No new frontend dependencies

---

## Out of scope

- Broker password encryption at rest (plaintext for now, noted as future work)
- Multi-broker per-namespace routing
- EMQX webhook → push-based branch discovery
- JSON Schema editor with visual form builder (plain textarea editor)
