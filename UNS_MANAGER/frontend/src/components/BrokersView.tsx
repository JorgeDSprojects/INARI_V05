import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";
import type { Broker, BrokerStatus, BrokerTestResult } from "../types/uns";

type FormState = {
  label: string; host: string; port: number; api_port: number;
  username: string; password: string; use_tls: boolean;
};

const EMPTY_FORM: FormState = {
  label: "", host: "", port: 1883, api_port: 18083,
  username: "", password: "", use_tls: false,
};

export function BrokersView() {
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [selected, setSelected] = useState<Broker | null>(null);
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<BrokerTestResult | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [opError, setOpError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setBrokers(await api.brokers.list());
      setLoadError(null);
    } catch {
      setLoadError("Failed to load brokers");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!selected) { setStatus(null); return; }
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await api.brokers.status(selected.id);
        if (!cancelled) setStatus(s);
      } catch {
        // Status fetch failed — keep last known status, retry on next interval
      }
    };
    poll();
    const id = setInterval(poll, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, [selected]);

  const handleCreate = async () => {
    if (!form.label.trim() || !form.host.trim()) return;
    setSaving(true);
    setOpError(null);
    try {
      const payload = {
        label: form.label.trim(), host: form.host.trim(),
        port: form.port, api_port: form.api_port,
        username: form.username || undefined, password: form.password || undefined,
        use_tls: form.use_tls,
      };
      const b = await api.brokers.create(payload);
      setBrokers(prev => [...prev, b]);
      setShowForm(false);
      setForm(EMPTY_FORM);
    } catch {
      setOpError("Failed to save broker");
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this broker?")) return;
    try {
      await api.brokers.delete(id);
      setBrokers(prev => prev.filter(b => b.id !== id));
      if (selected?.id === id) { setSelected(null); setStatus(null); }
    } catch {
      setOpError("Failed to delete broker");
    }
  };

  const handleTest = async () => {
    if (!selected) return;
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await api.brokers.test(selected.id));
    } catch {
      setOpError("Connection test failed");
    } finally { setTesting(false); }
  };

  const setField = (key: keyof FormState, val: string | number | boolean) =>
    setForm(prev => ({ ...prev, [key]: val }));

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left panel */}
      <div className="w-96 border-r border-border flex flex-col overflow-hidden bg-surface shrink-0">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold text-ink">Broker registry</h2>
          <button onClick={() => setShowForm(v => !v)}
            className="px-3 py-1.5 text-xs bg-ink text-white rounded hover:bg-ink/90">
            + Register broker
          </button>
        </div>

        {showForm && (
          <div className="px-5 py-4 border-b border-border space-y-3 bg-surface-subtle">
            {([
              { key: "label", label: "Label", type: "text", ph: "Production EMQX" },
              { key: "host", label: "Host", type: "text", ph: "emqx" },
              { key: "port", label: "MQTT Port", type: "number", ph: "1883" },
              { key: "api_port", label: "API Port", type: "number", ph: "18083" },
              { key: "username", label: "Username", type: "text", ph: "admin (optional)" },
              { key: "password", label: "Password", type: "password", ph: "••••••" },
            ] as const).map(f => (
              <div key={f.key}>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1">
                  {f.label.toUpperCase()}
                </label>
                <input type={f.type} placeholder={f.ph}
                  value={String(form[f.key as keyof FormState])}
                  onChange={e => setField(
                    f.key as keyof FormState,
                    f.type === "number" ? Number(e.target.value) : e.target.value
                  )}
                  className="w-full px-3 py-1.5 text-sm border border-border rounded bg-surface text-ink focus:outline-none focus:border-accent"
                />
              </div>
            ))}
            <label className="flex items-center gap-2 text-sm text-ink-secondary cursor-pointer">
              <input type="checkbox" checked={form.use_tls}
                onChange={e => setField("use_tls", e.target.checked)} />
              Use TLS
            </label>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={saving || !form.label || !form.host}
                className="px-3 py-1.5 text-xs bg-ink text-white rounded disabled:opacity-50">
                {saving ? "Saving…" : "Save broker"}
              </button>
              <button onClick={() => { setShowForm(false); setForm(EMPTY_FORM); }}
                className="px-3 py-1.5 text-xs text-ink-secondary border border-border rounded">
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {brokers.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-ink-muted text-sm py-12">
              {loadError
                ? <span className="text-danger text-center px-4">{loadError}</span>
                : <span>No brokers registered</span>
              }
            </div>
          ) : brokers.map(b => (
            <button key={b.id} onClick={() => { setSelected(b); setTestResult(null); }}
              className={`w-full text-left px-5 py-3.5 border-b border-border-subtle flex items-center justify-between group hover:bg-surface-subtle transition-colors ${selected?.id === b.id ? "bg-surface-subtle" : ""}`}>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink truncate">{b.label}</div>
                <div className="text-xs text-ink-muted font-mono">{b.host}:{b.port}</div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`w-2 h-2 rounded-full transition-colors ${
                  selected?.id === b.id && status
                    ? status.connected ? "bg-success" : "bg-danger"
                    : "bg-ink-muted/30"
                }`} />
                <button onClick={e => { e.stopPropagation(); handleDelete(b.id); }}
                  className="opacity-0 group-hover:opacity-100 text-danger text-[10px] px-1.5 py-0.5 rounded hover:bg-danger-soft transition-opacity">
                  ✕
                </button>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel */}
      {selected ? (
        <div className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-lg space-y-6">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-xl font-semibold text-ink">{selected.label}</h3>
                <div className="text-sm text-ink-muted font-mono mt-0.5">{selected.host}:{selected.port}</div>
              </div>
              {status && (
                <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium ${status.connected ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
                  <span className={`w-1.5 h-1.5 rounded-full inline-block ${status.connected ? "bg-success" : "bg-danger"}`} />
                  {status.connected ? "CONNECTED" : "DISCONNECTED"}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-x-8 gap-y-4">
              {([
                ["MQTT Port", String(selected.port)],
                ["API Port", String(selected.api_port)],
                ["TLS", selected.use_tls ? "Enabled" : "Disabled"],
                ["Username", selected.username ?? "—"],
                ["EMQX Version", status?.version ?? "—"],
                ["Node", status?.node ?? "—"],
              ] as [string, string][]).map(([k, v]) => (
                <div key={k}>
                  <div className="text-[10px] tracking-widest text-ink-muted mb-1">{k}</div>
                  <div className="text-sm text-ink font-mono">{v}</div>
                </div>
              ))}
            </div>

            <div>
              <button onClick={handleTest} disabled={testing}
                className="px-4 py-2 text-sm border border-border rounded text-ink hover:bg-surface-subtle disabled:opacity-50">
                {testing ? "Testing connection…" : "Test connection"}
              </button>
              {testResult && (
                <div className={`mt-3 px-4 py-3 rounded text-sm ${testResult.ok ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
                  {testResult.ok
                    ? `✓ Connected in ${testResult.latency_ms}ms`
                    : `✗ Failed — ${testResult.error}`}
                </div>
              )}
              {status?.error && !testResult && (
                <p className="mt-2 text-xs text-danger">{status.error}</p>
              )}
            </div>
            {opError && (
              <p className="text-sm text-danger">{opError}</p>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-ink-muted text-sm">
          Select a broker to view details
        </div>
      )}
    </div>
  );
}
