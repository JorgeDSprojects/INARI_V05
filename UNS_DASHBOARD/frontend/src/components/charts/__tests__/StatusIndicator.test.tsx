import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusIndicator } from "../StatusIndicator";

describe("StatusIndicator", () => {
  it("renders each state's label/value with its resolved color", () => {
    render(<StatusIndicator states={[{ label: "Bomba 1", value: "ON", color: "#17865D" }]} />);
    const value = screen.getByText("ON");
    expect(value).toHaveStyle({ color: "#17865D" });
  });
});
