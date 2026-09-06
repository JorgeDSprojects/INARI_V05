import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { ChatPanel } from "../ChatPanel";
import { api } from "../../../api/client";

vi.mock("../../../api/client", () => ({
  api: {
    chat: {
      status: vi.fn(),
      createSession: vi.fn(),
      sendMessage: vi.fn(),
    },
  },
}));

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state before the status check resolves, with no input or send button in the DOM", () => {
    // Never resolves during this test -- exercises the pre-status render.
    (api.chat.status as any).mockReturnValue(new Promise(() => {}));

    render(<ChatPanel onDashboardCreated={() => {}} />);

    expect(screen.getByText(/Comprobando el asistente/i)).toBeInTheDocument();
    expect(document.querySelector("input")).toBeNull();
    expect(document.querySelector("button")).toBeNull();
  });

  it("renders no message input or send button anywhere in the DOM, and shows the reason, when the assistant is unavailable", async () => {
    (api.chat.status as any).mockResolvedValue({ available: false, reason: "El modelo configurado no está disponible" });

    render(<ChatPanel onDashboardCreated={() => {}} />);

    await waitFor(() => expect(screen.getByText(/El modelo configurado no está disponible/)).toBeInTheDocument());

    // Absent, not merely disabled/hidden -- the headline constraint this
    // branch must protect (no-provider must never let the input be usable).
    expect(document.querySelector("input")).toBeNull();
    expect(document.querySelector("button")).toBeNull();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();

    // Being unavailable must never even attempt to open a chat session.
    expect(api.chat.createSession).not.toHaveBeenCalled();
  });

  it("becomes usable once the status is available and a session has been created", async () => {
    (api.chat.status as any).mockResolvedValue({ available: true, reason: null });
    (api.chat.createSession as any).mockResolvedValue({ id: "session-1" });

    render(<ChatPanel onDashboardCreated={() => {}} />);

    const input = await screen.findByPlaceholderText("Describe el dashboard que quieres…");
    await waitFor(() => expect(input).not.toBeDisabled());
    expect(screen.getByRole("button", { name: "Enviar" })).not.toBeDisabled();
    expect(api.chat.createSession).toHaveBeenCalledTimes(1);
  });

  it("keeps the input disabled while the session is still being created", async () => {
    (api.chat.status as any).mockResolvedValue({ available: true, reason: null });
    // Never resolves during this test -- session creation is in flight.
    (api.chat.createSession as any).mockReturnValue(new Promise(() => {}));

    render(<ChatPanel onDashboardCreated={() => {}} />);

    const input = await screen.findByPlaceholderText("Describe el dashboard que quieres…");
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
    expect(screen.getByText(/Iniciando conversación/i)).toBeInTheDocument();
  });
});
