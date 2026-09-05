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
