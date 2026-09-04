import type { ReactNode } from "react";
import type { ConnectionState } from "../lib/connectionState";

export function ChartCardShell({
  title,
  modeLabel,
  connectionState,
  editable,
  onRemove,
  onEdit,
  children,
}: {
  title: string;
  modeLabel: string;
  connectionState?: ConnectionState | null;
  editable: boolean;
  onRemove?: () => void;
  onEdit?: () => void;
  children: ReactNode;
}) {
  const badge = connectionState === "reconnecting"
    ? { text: "Reconectando…", cls: "bg-danger-soft text-danger" }
    : connectionState === "stale"
      ? { text: "Sin datos recientes", cls: "bg-warning-soft text-warning" }
      : { text: modeLabel, cls: modeLabel.startsWith("Live") ? "bg-success-soft text-success" : "bg-accent-soft text-accent" };

  return (
    <div className="h-full w-full bg-surface border border-border rounded-lg p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-bold text-ink">{title}</span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${badge.cls}`}>
            {badge.text}
          </span>
        </div>
        {editable && (
          <div className="flex items-center gap-2">
            {onEdit && <button onClick={onEdit} className="text-ink-muted text-xs">✎</button>}
            {onRemove && <button onClick={onRemove} className="text-ink-muted text-xs">✕</button>}
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}
