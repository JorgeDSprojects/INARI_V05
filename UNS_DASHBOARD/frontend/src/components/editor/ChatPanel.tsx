import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { ChatMessage, SignalCandidate } from "../../types/dashboard";

export function ChatPanel({
  dashboardId,
  onDashboardCreated,
  onDashboardChanged,
}: {
  /** The dashboard the user is currently editing, if any. Passed through to
   * the new session so the model knows to prefer editing THIS dashboard
   * instead of defaulting to creating a brand new one (see chat_agent's
   * _build_system_prompt). Also seeds reportedDashboardIdRef below, so the
   * panel doesn't mistake the chat successfully editing the dashboard the
   * user is already looking at for a brand new dashboard needing navigation. */
  dashboardId?: string;
  onDashboardCreated: (dashboardId: string) => void;
  /** Called whenever a turn changed something (actions is non-empty) on a
   * dashboard this session had already reported before -- i.e. every turn
   * after the one that first created/bound the dashboard. onDashboardCreated
   * only fires once per dashboard id (the backend returns the session's
   * dashboard_id on every turn, not just the one that created it), so
   * without this the editor's grid would only ever refresh after the very
   * first turn. */
  onDashboardChanged?: () => void;
}) {
  const [status, setStatus] = useState<{ available: boolean; reason: string | null } | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const reportedDashboardIdRef = useRef<string | null>(dashboardId ?? null);

  useEffect(() => {
    api.chat.status().then(setStatus).catch(() => setStatus({ available: false, reason: "No se pudo comprobar el estado del asistente." }));
  }, []);

  useEffect(() => {
    if (status?.available && !sessionId) {
      api.chat
        .createSession(dashboardId)
        .then((s) => setSessionId(s.id))
        .catch(() => setStatus({ available: false, reason: "No se pudo iniciar la sesión de chat." }));
    }
  }, [status, sessionId, dashboardId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
        <div ref={bottomRef} />
      </div>
      {error && <div className="px-3 text-xs text-danger">{error}</div>}
      {!sessionId && <div className="px-3 text-xs text-ink-muted">Iniciando conversación…</div>}
      <div className="flex gap-2 p-3 border-t border-border">
        <input
          className="flex-1 border border-border rounded-lg px-3 py-2 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Describe el dashboard que quieres…"
          disabled={sending || !sessionId}
        />
        <button className="px-4 py-2 text-sm rounded-lg bg-brand text-white disabled:opacity-50" onClick={() => send()} disabled={sending || !sessionId}>
          Enviar
        </button>
      </div>
    </div>
  );
}
