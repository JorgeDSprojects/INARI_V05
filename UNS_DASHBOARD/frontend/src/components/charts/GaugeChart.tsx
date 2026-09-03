import type { ChartSignal } from "../../types/dashboard";

export function GaugeChart({ signal, value }: { signal: ChartSignal; value: number }) {
  const min = signal.min ?? 0;
  const max = signal.max ?? 100;
  const ratio = Math.min(1, Math.max(0, (value - min) / (max - min || 1)));
  const sweep = 270 * ratio;

  const arcPath = (startDeg: number, sweepDeg: number, r: number) => {
    const toRad = (d: number) => (d * Math.PI) / 180;
    const cx = 50, cy = 50;
    const x1 = cx + r * Math.cos(toRad(startDeg));
    const y1 = cy - r * Math.sin(toRad(startDeg));
    const endDeg = startDeg - sweepDeg;
    const x2 = cx + r * Math.cos(toRad(endDeg));
    const y2 = cy - r * Math.sin(toRad(endDeg));
    const largeArc = sweepDeg > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  return (
    <div className="h-full flex flex-col items-center justify-center gap-1">
      <svg viewBox="0 0 100 100" className="w-32 h-32">
        <path d={arcPath(225, 270, 40)} stroke="#DDE2E7" strokeWidth={10} fill="none" strokeLinecap="round" />
        <path d={arcPath(225, sweep, 40)} stroke={signal.color ?? "#198ACB"} strokeWidth={10} fill="none" strokeLinecap="round" />
      </svg>
      <span className="text-2xl font-bold text-ink -mt-16">{value}{signal.unit}</span>
      <span className="text-xs text-ink-secondary mt-16">{signal.label ?? signal.signal_key}</span>
    </div>
  );
}
