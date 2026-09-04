export type ConnectionState = "live" | "stale" | "reconnecting";

const STALE_AFTER_MS = 15_000;

export function computeConnectionState(
  wsOpen: boolean,
  topics: string[],
  lastFrameAt: Record<string, number>,
  connectedAt: number,
  now: number,
  staleAfterMs: number = STALE_AFTER_MS
): ConnectionState {
  if (!wsOpen) return "reconnecting";
  if (topics.length === 0) return "live";
  const freshest = Math.max(connectedAt, ...topics.map((t) => lastFrameAt[t] ?? 0));
  return now - freshest > staleAfterMs ? "stale" : "live";
}
