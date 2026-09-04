import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { pollIntervalMsFor } from "../lib/refreshInterval";
import type { HistoricalRangeType, HistoryPoint, RelativeRule } from "../types/dashboard";

export interface HistoricalQueryResult {
  points: HistoryPoint[];
  error: boolean;
  retry: () => void;
}

export function useHistoricalQuery(
  chartId: string,
  rangeType: HistoricalRangeType | null | undefined,
  relativeRule: RelativeRule | null | undefined
): HistoricalQueryResult {
  const [points, setPoints] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState(false);
  const [retryTick, setRetryTick] = useState(0);

  const retry = useCallback(() => setRetryTick((n) => n + 1), []);

  useEffect(() => {
    if (!rangeType) return;

    let cancelled = false;
    const fetchOnce = () => {
      api.history.get(chartId).then((res) => {
        if (cancelled) return;
        setPoints(res.points);
        setError(false);
      }).catch(() => {
        if (cancelled) return;
        setError(true);
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
  }, [chartId, rangeType, relativeRule, retryTick]);

  return { points, error, retry };
}
