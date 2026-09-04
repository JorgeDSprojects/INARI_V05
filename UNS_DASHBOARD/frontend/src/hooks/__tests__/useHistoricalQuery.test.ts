import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useHistoricalQuery } from "../useHistoricalQuery";
import { api } from "../../api/client";

vi.mock("../../api/client", () => ({
  api: { history: { get: vi.fn() } },
}));

describe("useHistoricalQuery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("returns points on a successful fetch", async () => {
    (api.history.get as any).mockResolvedValue({ points: [{ time: "t", v: 1 }] });
    const { result } = renderHook(() => useHistoricalQuery("chart-1", "fixed", null));
    await waitFor(() => expect(result.current.points).toEqual([{ time: "t", v: 1 }]));
    expect(result.current.error).toBe(false);
  });

  it("sets error and keeps points empty on a failed fetch", async () => {
    (api.history.get as any).mockRejectedValue(new Error("network"));
    const { result } = renderHook(() => useHistoricalQuery("chart-1", "fixed", null));
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.points).toEqual([]);
  });

  it("retry re-fetches and clears the error once it succeeds", async () => {
    (api.history.get as any)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ points: [{ time: "t", v: 2 }] });
    const { result } = renderHook(() => useHistoricalQuery("chart-1", "fixed", null));
    await waitFor(() => expect(result.current.error).toBe(true));

    result.current.retry();

    await waitFor(() => expect(result.current.error).toBe(false));
    expect(result.current.points).toEqual([{ time: "t", v: 2 }]);
  });

  it("does not fetch when rangeType is null", () => {
    renderHook(() => useHistoricalQuery("chart-1", null, null));
    expect(api.history.get).not.toHaveBeenCalled();
  });
});
