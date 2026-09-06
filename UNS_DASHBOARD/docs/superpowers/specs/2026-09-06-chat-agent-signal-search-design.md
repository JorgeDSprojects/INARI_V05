# Chat Agent Signal Search & Candidate Disambiguation — Design

**Status:** Approved (sections A/B/C confirmed in chat).

## Problem

The chat agent's only way to discover signals is `UNS_MCP`'s `list_signals(topic_prefix)`,
which filters `signal_catalog.topic` with `WHERE topic LIKE prefix + '%'` — a match
from the *start* of the asset-hierarchy path, never a name search. Live testing (see
`2026-09-06-uns-dashboard-chat-agent.md`'s post-ship fix rounds) confirmed this breaks
ordinary requests:

- "Generador" → the real topic ends in `.../GENERATOR` (uppercase, and at the END of
  the path) — a prefix match can never find it regardless of translation accuracy.
- "rpm medios del generador" → no single guessable `topic_prefix` exists at all.

No amount of system-prompt tuning fixes this: `topic_prefix` is structurally the
wrong filter for a name-based question. Separately, when a user's request IS
resolvable but ambiguously (multiple similarly-named signals, multiple assets), the
chat currently has no way to let the user disambiguate except through free-text
back-and-forth — which the deployed pilot model (`qwen2.5:14b-instruct`) already
handles unreliably (see the `chat-agent-fixes` worktree's fix-round history).

## Approach

Two additive pieces, chosen over pure prompt-engineering (Option A, rejected — already
proven unreliable) and over a fully non-LLM candidate-resolution flow (Option C,
deferred — more robust but requires new session-side pending-write state; revisit if
Option B proves insufficiently reliable in practice):

1. **A real search tool in `UNS_MCP`**: `search_signals(query, limit=10)`, matching
   substrings (case-insensitive) across `signal_key`, `description`, and the full
   `topic` string — not just a path prefix.
2. **A structured candidate-presentation mechanism in the chat agent**: when the
   model isn't confident of a single match, it calls a new `present_signal_candidates`
   tool instead of guessing. The backend intercepts this specially, ends the turn
   immediately, and returns the candidates as structured data (not text) that the
   frontend renders as clickable buttons. Picking one sends an unambiguous follow-up
   message — a far easier task for the model than resolving ambiguity from scratch.

## A. `search_signals` (new tool, `UNS_MCP`)

```python
# UNS_MCP/server/app/db.py
def search_signals(conn: psycopg.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Case-insensitive substring search across signal_key, description, and the
    full topic path -- unlike list_signals' path-prefix filter, this can find a
    signal by name or partial name regardless of where it sits in the hierarchy."""
```

- Splits `query` into whitespace-separated words; for each word, builds an
  `ILIKE '%word%'` clause against `signal_key`, `topic`, and `description`
  (parameterized, no string interpolation into SQL).
- Score per row: sum, across words, of (3 if `signal_key` matched, 2 if `topic`
  matched, 1 if `description` matched, 0 otherwise). Ties broken by `topic, signal_key`.
- `WHERE effective_until IS NULL AND (<any word matched any field>)`, `ORDER BY score
  DESC, topic, signal_key`, `LIMIT %(limit)s`.
- Returns the same shape as `list_signals` plus `score`: `{topic, signal_key,
  signal_type, unit, description, score}`.
- Exposed as `@mcp.tool()` in `server.py`, docstring explicitly telling the caller
  this is a name/keyword search (contrast with `list_signals`' path-prefix search) and
  that multi-word queries should be keywords, not full sentences.

**Known limitation, accepted for this iteration**: a single query string with several
unrelated keywords (e.g. "rpm medios del generador") scores partial matches per word
without understanding relationships between them — good enough for the 1-3 keyword
case the system prompt will ask for, not a general NL search engine. If this proves
insufficient in practice, `pg_trgm`-based fuzzy similarity is the natural next
iteration (out of scope here).

## B. Candidate presentation (chat agent + protocol + frontend)

**New tool** (in `chat_agent.py`, alongside `_WRITE_TOOLS` but in its own category —
never a DB write, never forwarded to MCP):

```python
_PRESENT_CANDIDATES_TOOL = {
    "type": "function",
    "function": {
        "name": "present_signal_candidates",
        "description": (
            "Call this INSTEAD of guessing when search_signals returned 2+ plausible "
            "matches, or you are not confident which single one the user means. Do "
            "NOT call this for a single unambiguous match -- just use that signal "
            "directly. The candidates are shown to the user as clickable options; "
            "you do not need to ask a follow-up question yourself."
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
```

**Dispatch (`run_turn`)**: when a response's `tool_calls` includes
`present_signal_candidates`, the turn ends immediately after processing it — no
further iterations, regardless of `_MAX_ITERATIONS` or other tool calls in the same
batch. Validation before accepting: `candidates` must be non-empty (a tool-error
result if empty, looping back to the model rather than surfacing zero buttons) and is
truncated server-side to a max of 8 entries (defensive cap, independent of
`search_signals`' own `limit`).

**Return shape**: `run_turn` gains a 5th tuple element:
```python
async def run_turn(...) -> tuple[str, list[dict], str | None, list[str], list[dict] | None]:
    # (reply_text, new_messages, dashboard_id, actions, candidates)
```
`candidates` is `None` on every turn that doesn't call `present_signal_candidates`,
and the resolved list (dicts matching the schema above) otherwise.

**Schema (`app/schemas/chat.py`)**:
```python
class SignalCandidate(BaseModel):
    topic: str
    signal_key: str
    signal_type: str | None = None
    unit: str | None = None
    description: str | None = None

class ChatMessageResponse(BaseModel):
    reply: str
    dashboard_id: str | None
    actions: list[str]
    candidates: list[SignalCandidate] | None = None
```
Candidates are also persisted into the assistant's stored `ChatMessage.content` (so
the conversation-history viewer, already shipped, can show them on a revisited
session) as an extra `candidates` key alongside the existing `role`/`content` shape.

**Frontend (`ChatPanel.tsx`)**: each rendered message can carry an optional
`candidates` array; when present, render one button per candidate (label: a short
readable form, e.g. `"{signal_key} — {topic}"` truncated). Clicking a button composes
a fixed, unambiguous message —
`"Usa la señal {signal_key} en {topic}"` — and sends it immediately (one click, no
retyping), reusing the existing `send()` path so the model's next turn resolves it
like any other confirmed instruction.

## C. Error handling & testing

- `search_signals` returning nothing (even split by word): the model declines
  gracefully and asks the user to rephrase — same pattern already in the system
  prompt for `list_signals`.
- `present_signal_candidates` with an empty list: rejected as a tool-error, fed back
  to the model (never surfaced as an empty button row to the user).
- A candidate list beyond 8 entries: truncated server-side, never rejected outright.
- Any transport/DB error from `search_signals`/MCP: falls into the loop's existing
  generic exception-to-tool-error handling — no new error path needed.
- Testing follows each layer's existing convention exactly (no new pattern introduced):
  - `UNS_MCP/server/tests/test_db.py`: new `search_signals` cases against the live
    `SILVER_DATABASE_URL`/`SEED_DATABASE_URL` fixture (case-insensitivity, multi-word
    scoring/ordering, `limit` respected, `effective_until` filtering preserved).
  - `UNS_DASHBOARD/backend/tests/test_chat_agent.py`: scripted-provider tests
    confirming `present_signal_candidates` ends the turn with `candidates` populated,
    an empty-candidates call is rejected as a tool error, and a normal write-tool turn
    is unaffected (`candidates is None`).
  - `UNS_DASHBOARD/frontend/.../ChatPanel.test.tsx`: candidate buttons render from a
    mocked response, and clicking one calls `sendMessage` with the expected canned text.

## Deferred (explicitly out of scope this iteration)

- Option C (candidate selection bypassing the LLM entirely via server-side pending-write
  state) — revisit only if Option B's one-more-LLM-round-trip proves unreliable in
  practice.
- Hierarchical/guided narrowing (asset-level candidate chips before signal-level ones)
  when `search_signals` itself returns too many matches to present directly — the
  same UI mechanism, applied recursively; not built this iteration.
- `pg_trgm`-based fuzzy similarity scoring (only substring/ILIKE this iteration).
