import { describe, expect, it } from "vitest";
import { computeConnectionState } from "../connectionState";

describe("computeConnectionState", () => {
  it("is reconnecting when the socket is not open", () => {
    expect(computeConnectionState(false, ["t"], {}, 0, 1000)).toBe("reconnecting");
  });

  it("is live right after connecting, before any frame has arrived", () => {
    expect(computeConnectionState(true, ["t"], {}, 1000, 1005)).toBe("live");
  });

  it("is live when a frame arrived recently", () => {
    expect(computeConnectionState(true, ["t"], { t: 1000 }, 0, 1005)).toBe("live");
  });

  it("is stale once the freshest frame is older than the threshold", () => {
    expect(computeConnectionState(true, ["t"], { t: 1000 }, 0, 1000 + 15_001)).toBe("stale");
  });

  it("is live with no configured topics -- nothing to be stale about", () => {
    expect(computeConnectionState(true, [], {}, 0, 999_999)).toBe("live");
  });

  it("takes the freshest of multiple topics", () => {
    expect(computeConnectionState(true, ["a", "b"], { a: 1000, b: 16_000 }, 0, 16_001)).toBe("live");
  });
});
