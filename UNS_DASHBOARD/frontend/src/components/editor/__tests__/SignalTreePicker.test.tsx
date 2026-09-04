import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignalTreePicker } from "../SignalTreePicker";
import { api } from "../../../api/client";

vi.mock("../../../api/client", () => ({
  api: {
    signals: {
      treeHistorical: vi.fn(),
      treeLive: vi.fn(),
      descriptive: vi.fn(),
    },
  },
}));

const tree = [{
  segment: "Planta1",
  children: [{
    segment: "_informative",
    children: [],
    leaf: { topic: "Planta1/_informative", topic_type: "informative" as const, keys: ["Gen_RPM_Avg"] },
  }],
}];

describe("SignalTreePicker", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("lists a leaf's keys as addable buttons once the historical tree loads", async () => {
    (api.signals.treeHistorical as any).mockResolvedValue(tree);
    render(<SignalTreePicker source="historical" selected={[]} chartColor={null} onChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("+ Gen_RPM_Avg")).toBeInTheDocument());
  });

  it("calls the live tree endpoint when source is live", async () => {
    (api.signals.treeLive as any).mockResolvedValue([]);
    render(<SignalTreePicker source="live" selected={[]} chartColor={null} onChange={() => {}} />);
    await waitFor(() => expect(api.signals.treeLive).toHaveBeenCalled());
    expect(api.signals.treeHistorical).not.toHaveBeenCalled();
  });

  it("adds a signal with descriptive metadata prefill, stripping the _informative suffix", async () => {
    (api.signals.treeHistorical as any).mockResolvedValue(tree);
    (api.signals.descriptive as any).mockResolvedValue({ unit: "rpm" });
    const onChange = vi.fn();
    render(<SignalTreePicker source="historical" selected={[]} chartColor={null} onChange={onChange} />);
    fireEvent.click(await screen.findByText("+ Gen_RPM_Avg"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ topic: "Planta1/_informative", signal_key: "Gen_RPM_Avg", unit: "rpm", source: "auto" }),
    ]));
    expect(api.signals.descriptive).toHaveBeenCalledWith("Planta1", "Gen_RPM_Avg");
  });

  it("shows an inline error when the tree fetch fails", async () => {
    (api.signals.treeHistorical as any).mockRejectedValue(new Error("network"));
    render(<SignalTreePicker source="historical" selected={[]} chartColor={null} onChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("No se pudo cargar el árbol histórico.")).toBeInTheDocument());
  });
});
