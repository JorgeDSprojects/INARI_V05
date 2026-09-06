import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { ChatSessionDetail, ChatSessionSummary } from "../../types/dashboard";

/** Renders one saved chat message. Messages stored by the backend are the
 * raw provider-loop envelope (see chat_agent.run_turn), not the simplified
 * `{ text }` shape ChatPanel builds for its own live rendering:
 *  - user/assistant text turns: { role, content: "some text" }
 *  - assistant tool-call turns: { role: "assistant", content, tool_calls: [...] }
 *  - tool results: { role: "tool", tool_call_id, content: "json string" }
 * so this renders `content.content` when it's a string, and falls back to a
 * compact summary for tool calls/results instead of crashing on them. */
function MessageBubble({ message }: { message: { role: string; content: Record<string, unknown> } }) {
  const { role, content } = message;
  const text = typeof content.content === "string" ? content.content : null;
  const toolCalls = Array.isArray(content.tool_calls) ? (content.tool_calls as Array<Record<string, unknown>>) : null;

  let body: string;
  if (role === "tool") {
    body = `🔧 resultado: ${text ?? JSON.stringify(content.content ?? content)}`;
  } else if (toolCalls && toolCalls.length > 0) {
    const names = toolCalls
      .map((tc) => (tc.function as Record<string, unknown> | undefined)?.name ?? "?")
      .join(", ");
    body = text ? `${text}\n🔧 llamó a: ${names}` : `🔧 llamó a: ${names}`;
  } else {
    body = text ?? "(sin contenido)";
  }

  const isUser = role === "user";
  return (
    <div
      className={`text-sm rounded-lg px-3 py-2 max-w-[85%] whitespace-pre-wrap ${
        isUser ? "self-end bg-brand text-white" : "self-start bg-surface"
      }`}
    >
      {body}
    </div>
  );
}

function SessionRow({ session }: { session: ChatSessionSummary }) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<ChatSessionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !detail) {
      setLoading(true);
      setError(null);
      api.chat
        .getSession(session.id)
        .then(setDetail)
        .catch(() => setError("No se pudo cargar esta conversación."))
        .finally(() => setLoading(false));
    }
  };

  return (
    <div className="border border-border rounded-lg">
      <button
        type="button"
        onClick={toggle}
        className="w-full text-left px-3 py-2 text-sm flex flex-col gap-0.5"
      >
        <span className="text-xs text-ink-muted">{new Date(session.created_at).toLocaleString()}</span>
        <span className="truncate">{session.first_user_message ?? "(sin mensajes)"}</span>
      </button>
      {expanded && (
        <div className="border-t border-border p-3 flex flex-col gap-2 max-h-72 overflow-y-auto">
          {loading && <span className="text-xs text-ink-muted">Cargando…</span>}
          {error && <span className="text-xs text-danger">{error}</span>}
          {detail?.messages.map((m, i) => <MessageBubble key={i} message={m} />)}
          {detail && detail.messages.length === 0 && (
            <span className="text-xs text-ink-muted">Esta conversación no tiene mensajes.</span>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatHistoryPanel({ dashboardId }: { dashboardId: string }) {
  const [sessions, setSessions] = useState<ChatSessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    setSessions(null);
    setError(null);
    api.chat
      .listSessions(dashboardId)
      .then(setSessions)
      .catch(() => setError("No se pudo cargar el historial de conversaciones."));
  }, [dashboardId]);

  return (
    <div className="border border-border rounded-lg">
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="w-full text-left px-3 py-2 text-xs font-bold text-ink-muted uppercase flex justify-between items-center"
      >
        <span>Historial de conversaciones</span>
        <span>{collapsed ? "▸" : "▾"}</span>
      </button>
      {!collapsed && (
        <div className="border-t border-border p-3 flex flex-col gap-2">
          {error && <div className="text-xs text-danger">{error}</div>}
          {!error && sessions === null && <div className="text-xs text-ink-muted">Cargando…</div>}
          {sessions && sessions.length === 0 && (
            <div className="text-xs text-ink-muted">Aún no hay conversaciones registradas para este dashboard.</div>
          )}
          {sessions?.map((s) => <SessionRow key={s.id} session={s} />)}
        </div>
      )}
    </div>
  );
}
