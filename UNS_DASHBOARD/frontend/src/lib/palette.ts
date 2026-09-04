import type { ChartSignal } from "../types/dashboard";

export const DEFAULT_PALETTE = [
  "#198ACB", "#17865D", "#A9630B", "#C43F3F",
  "#6D5BD0", "#0E9F9F", "#B0538B", "#5E6872",
];

export function resolveColor(
  signal: ChartSignal,
  chartColor: string | null | undefined,
  index: number,
  total: number
): string {
  if (signal.color) return signal.color;
  if (total === 1 && chartColor) return chartColor;
  return DEFAULT_PALETTE[index % DEFAULT_PALETTE.length];
}
