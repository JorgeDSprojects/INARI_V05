import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TimeSeriesChart } from "../TimeSeriesChart";

describe("TimeSeriesChart", () => {
  it("renders a legend entry per signal", () => {
    render(
      <TimeSeriesChart
        signals={[{ topic: "a", signal_key: "Amb_Temp_Avg", label: "Amb Temp", color: "#3B82F6" }]}
        points={[{ time: "2026-09-03T10:00:00Z", Amb_Temp_Avg: 19 }]}
      />
    );
    expect(screen.getByText("Amb Temp")).toBeInTheDocument();
  });
});
