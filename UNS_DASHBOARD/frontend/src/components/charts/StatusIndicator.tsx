export function StatusIndicator({ states }: { states: { label: string; value: string; color: string }[] }) {
  return (
    <div className="h-full flex flex-col justify-center gap-2">
      {states.map((s) => (
        <div key={s.label} className="flex items-center justify-between bg-surface-subtle rounded px-3 py-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
            <span className="text-xs text-ink">{s.label}</span>
          </div>
          <span className="text-xs font-bold" style={{ color: s.color }}>{s.value}</span>
        </div>
      ))}
    </div>
  );
}
