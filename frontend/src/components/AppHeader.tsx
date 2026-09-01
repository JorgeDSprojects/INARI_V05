import type { AppView } from "../App";
import type { EnterpriseTree } from "../types/uns";

interface Props {
  view: AppView;
  setView: (v: AppView) => void;
  activeEnterprise: EnterpriseTree | null;
  onBack: () => void;
}

const NAV = [
  { id: "catalog", label: "Namespaces" },
  { id: "brokers", label: "Brokers" },
  { id: "nodetypes", label: "Node types" },
] as const;

export function AppHeader({ view, setView, activeEnterprise, onBack }: Props) {
  return (
    <header className="flex items-center justify-between px-6 bg-surface border-b border-border h-16 shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div
          className="w-7 h-7 rounded bg-ink flex items-center justify-center cursor-pointer"
          onClick={onBack}
        >
          <span className="text-white text-xs font-bold">U</span>
        </div>
        <div className="flex flex-col leading-none">
          <span className="text-ink font-semibold text-sm tracking-tight">UNS MANAGER</span>
          <span className="text-ink-muted text-[10px] tracking-widest">CONTROL PLANE</span>
        </div>
      </div>

      {/* Nav tabs (only in catalog-level views) */}
      {view !== "workspace" && (
        <nav className="flex items-center h-full gap-1">
          {NAV.map(item => (
            <button
              key={item.id}
              onClick={() => setView(item.id as AppView)}
              className={`px-4 h-full text-sm border-b-2 transition-colors ${
                view === item.id
                  ? "border-ink text-ink font-medium"
                  : "border-transparent text-ink-secondary hover:text-ink"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      )}

      {/* Breadcrumbs in workspace */}
      {view === "workspace" && activeEnterprise && (
        <nav className="flex items-center gap-2 text-sm">
          <button onClick={onBack} className="text-ink-secondary hover:text-ink">
            Namespaces
          </button>
          <span className="text-ink-muted">›</span>
          <span className="text-ink font-medium">{activeEnterprise.name}</span>
        </nav>
      )}

      {/* Right actions */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-success-soft text-success text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
          EMQX SYNCED
        </div>
        <div className="w-7 h-7 rounded-full bg-surface-muted flex items-center justify-center text-ink text-xs font-semibold">
          JM
        </div>
      </div>
    </header>
  );
}
