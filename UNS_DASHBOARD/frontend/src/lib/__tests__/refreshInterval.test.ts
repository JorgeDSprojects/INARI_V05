import { describe, expect, it } from "vitest";
import { pollIntervalMsFor } from "../refreshInterval";

describe("pollIntervalMsFor", () => {
  it("polls a 1h window every 30s", () => {
    expect(pollIntervalMsFor("1h")).toBe(30_000);
  });

  it("polls a 30d window every 10 minutes", () => {
    expect(pollIntervalMsFor("30d")).toBe(600_000);
  });
});
