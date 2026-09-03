import { useEffect, useState } from "react";
import { api } from "../api/client";
import { pollIntervalMsFor } from "../lib/refreshInterval";
import type { HistoricalRangeType, HistoryPoint, RelativeRule } from "../types/dashboard";

export function useHistoricalQuery(
  chartId: string,
  rangeType: HistoricalRangeType | null | undefined,
  relativeRule: RelativeRule | null | undefined
): HistoryPoint[] {
  const [points, setPoints] = useState<HistoryPoint[]>([]);

  useEffect(() => {
    if (!rangeType) return;

    let cancelled = false;
    const fetchOnce = () => {
      api.history.get(chartId).then((res) => {
        if (!cancelled) setPoints(res.points);
      }).catch(() => {
        /* leave points as-is; a transient fetch failure shouldn't crash the chart */
      });
    };
    fetchOnce();

    if (rangeType === "relative" && relativeRule) {
      const interval = setInterval(fetchOnce, pollIntervalMsFor(relativeRule));
      return () => {
        cancelled = true;
        clearInterval(interval);
      };
    }
    return () => {
      cancelled = true;
    };
  }, [chartId, rangeType, relativeRule]);

  return points;
}
