import type { RelativeRule } from "../types/dashboard";

const INTERVALS_MS: Record<RelativeRule, number> = {
  "1h": 30_000,
  "24h": 120_000,
  "7d": 300_000,
  "30d": 600_000,
};

export function pollIntervalMsFor(rule: RelativeRule): number {
  return INTERVALS_MS[rule];
}
