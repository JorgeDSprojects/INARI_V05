import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { Broker, BrokerStatus } from "../types/uns";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

export function CreateUnsWizard({ onClose, onCreated }: Props) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [broker, setBroker] = useState<Broker | null>(null);
  const [brokerStatus, setBrokerStatus] = useState<BrokerStatus | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const rootTopic = name.trim()
    ? name.trim().toLowerCase().replace(/\s+/g, "_")
    : "…";

  useEffect(() => {
    api.brokers.list()
      .then(list => {
        if (list.length > 0) {
          setBroker(list[0]);
          return api.brokers.status(list[0].id).then(setBrokerStatus);
        }
      })
      .catch(() => {
        // Network failure — leave broker null, Step 2 will show "No broker configured"
        // This is acceptable: user sees the same warning, can go to Brokers tab
      });
  }, []);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await api.enterprises.create({ name: name.trim(), description: description.trim() || undefined });
      onCreated();
      onClose();
    } catch {
      setCreateError("Failed to create namespace. Please try again.");
    } finally {
      setCreating(false);
    }
  };

  const STEPS = ["Name", "Broker", "Confirm"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-surface rounded-xl border border-border w-full max-w-lg shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-ink">Create Unified Namespace</h2>
          <button onClick={onClose} className="text-ink-muted hover:text-ink text-lg leading-none">✕</button>
        </div>

        {/* Stepper */}
        <div className="flex items-center gap-0 px-6 pt-5 pb-4">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center">
              <div className={`flex items-center gap-2 ${i < step ? "text-success" : i === step ? "text-ink" : "text-ink-muted"}`}>
                <span className={`w-6 h-6 rounded-full text-xs flex items-center justify-center font-medium border ${
                  i < step ? "bg-success text-white border-success" :
                  i === step ? "bg-ink text-white border-ink" :
                  "border-border-subtle text-ink-muted"
                }`}>
                  {i < step ? "✓" : i + 1}
                </span>
                <span className="text-sm">{label}</span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-12 h-px mx-3 ${i < step ? "bg-success" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="px-6 pb-6 min-h-[200px]">
          {step === 0 && (
            <div className="space-y-4 pt-2">
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">NAMESPACE NAME *</label>
                <input autoFocus type="text" placeholder="ACME Corporation"
                  value={name} onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && name.trim() && setStep(1)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
              </div>
              <div>
                <label className="text-[10px] tracking-widest text-ink-muted block mb-1.5">DESCRIPTION</label>
                <input type="text" placeholder="Optional description"
                  value={description} onChange={e => setDescription(e.target.value)}
                  className="w-full px-3 py-2 border border-border rounded text-sm text-ink bg-surface focus:outline-none focus:border-accent" />
              </div>
              {name.trim() && (
                <div className="flex items-center gap-1.5 px-3 py-2 rounded bg-surface-subtle w-fit">
                  <span className="text-accent text-[10px]">◈</span>
                  <span className="text-ink-secondary text-xs font-mono">{rootTopic}/…</span>
                </div>
              )}
            </div>
          )}

          {step === 1 && (
            <div className="space-y-4 pt-2">
              <p className="text-sm text-ink-secondary">
                This namespace will publish to the configured EMQX broker.
              </p>
              {broker ? (
                <div className="border border-border rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-ink">{broker.label}</span>
                    {brokerStatus && (
                      <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-medium ${brokerStatus.connected ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${brokerStatus.connected ? "bg-success" : "bg-danger"}`} />
                        {brokerStatus.connected ? "CONNECTED" : "DISCONNECTED"}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-ink-muted font-mono">{broker.host}:{broker.port}</div>
                </div>
              ) : (
                <div className="border border-warning/30 rounded-lg p-4 bg-warning-soft">
                  <p className="text-sm text-warning">No broker configured. Go to the Brokers tab to register one.</p>
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4 pt-2">
              <p className="text-sm text-ink-secondary">Review and confirm the new namespace.</p>
              <div className="border border-border rounded-lg divide-y divide-border-subtle">
                {[
                  ["Name", name],
                  ["Root MQTT topic", rootTopic],
                  ["Description", description || "—"],
                  ["Broker", broker?.label ?? "None configured"],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between px-4 py-3">
                    <span className="text-xs text-ink-muted">{k}</span>
                    <span className="text-sm text-ink font-mono text-right max-w-xs truncate">{v}</span>
                  </div>
                ))}
              </div>
              {createError && (
                <p className="text-sm text-danger mt-3">{createError}</p>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-surface-subtle">
          <button onClick={() => step > 0 ? setStep(step - 1) : onClose()}
            className="px-4 py-2 text-sm text-ink-secondary border border-border rounded hover:bg-surface">
            {step === 0 ? "Cancel" : "Back"}
          </button>
          <div className="flex items-center gap-2">
            {step < 2 ? (
              <button onClick={() => setStep(step + 1)} disabled={step === 0 && !name.trim()}
                className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50 hover:bg-ink/90">
                Next
              </button>
            ) : (
              <button onClick={handleCreate} disabled={creating}
                className="px-5 py-2 text-sm bg-ink text-white rounded disabled:opacity-50 hover:bg-ink/90">
                {creating ? "Creating…" : "Create namespace"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
