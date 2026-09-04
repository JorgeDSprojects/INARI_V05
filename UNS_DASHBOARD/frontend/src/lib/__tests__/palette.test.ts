import { describe, expect, it } from "vitest";
import { DEFAULT_PALETTE, resolveColor } from "../palette";
import type { ChartSignal } from "../../types/dashboard";

const signal = (color?: string | null): ChartSignal => ({ topic: "a", signal_key: "k", color: color ?? null });

describe("resolveColor", () => {
  it("prefers an explicit signal color override", () => {
    expect(resolveColor(signal("#FF0000"), "#000000", 0, 2)).toBe("#FF0000");
  });

  it("falls back to the chart color when there is exactly one signal", () => {
    expect(resolveColor(signal(), "#123456", 0, 1)).toBe("#123456");
  });

  it("falls back to the rotating palette by index for multi-signal charts", () => {
    expect(resolveColor(signal(), "#123456", 1, 3)).toBe(DEFAULT_PALETTE[1]);
  });

  it("wraps the palette index when there are more signals than colors", () => {
    const i = DEFAULT_PALETTE.length;
    expect(resolveColor(signal(), null, i, 10)).toBe(DEFAULT_PALETTE[0]);
  });

  it("uses the palette when there is one signal but no chart color set", () => {
    expect(resolveColor(signal(), null, 0, 1)).toBe(DEFAULT_PALETTE[0]);
  });
});
