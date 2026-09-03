import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GaugeChart } from "../GaugeChart";

describe("GaugeChart", () => {
  it("renders the current value and signal label", () => {
    render(<GaugeChart signal={{ topic: "a", signal_key: "Amb_Temp_Avg", label: "Amb Temp", unit: "°C", min: -20, max: 120 }} value={19} />);
    expect(screen.getByText("19°C")).toBeInTheDocument();
    expect(screen.getByText("Amb Temp")).toBeInTheDocument();
  });
});
