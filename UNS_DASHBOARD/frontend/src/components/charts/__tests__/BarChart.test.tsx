import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarChart } from "../BarChart";

describe("BarChart", () => {
  it("renders an svg chart without crashing", () => {
    const { container } = render(
      <BarChart
        signals={[{ topic: "a", signal_key: "Gen_RPM_Avg", label: "RPM", color: "#198ACB" }]}
        values={{ Gen_RPM_Avg: 1300 }}
      />
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});
