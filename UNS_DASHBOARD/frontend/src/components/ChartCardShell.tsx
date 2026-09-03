import type { ReactNode } from "react";

export function ChartCardShell({
  title,
  modeLabel,
  editable,
  onRemove,
  children,
}: {
  title: string;
  modeLabel: string;
  editable: boolean;
  onRemove?: () => void;
  children: ReactNode;
}) {
  const isLive = modeLabel.startsWith("Live");
  return (
    <div className="h-full w-full bg-surface border border-border rounded-lg p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-bold text-ink">{title}</span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-fit ${isLive ? "bg-success-soft text-success" : "bg-accent-soft text-accent"}`}>
            {modeLabel}
          </span>
        </div>
        {editable && onRemove && (
          <button onClick={onRemove} className="text-ink-muted text-xs">✕</button>
        )}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}
