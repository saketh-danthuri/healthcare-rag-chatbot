import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "./Sidebar";
import type { ChatSession } from "@/lib/types";

const sessions: ChatSession[] = [
  {
    id: "s1",
    title: "Claims triage",
    createdAt: new Date("2026-01-01T10:00:00Z"),
    messages: [],
  },
  {
    id: "s2",
    title: "Runbook lookup",
    createdAt: new Date("2026-01-01T11:00:00Z"),
    messages: [],
  },
];

function setup(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props = {
    sessions,
    activeSessionId: "s1",
    onNewChat: vi.fn(),
    onSelectSession: vi.fn(),
    onDeleteSession: vi.fn(),
    onRenameSession: vi.fn(),
    ...overrides,
  };
  render(<Sidebar {...props} />);
  return props;
}

describe("Sidebar rendering & selection", () => {
  it("lists all conversation titles", () => {
    setup();
    expect(screen.getByText("Claims triage")).toBeInTheDocument();
    expect(screen.getByText("Runbook lookup")).toBeInTheDocument();
  });

  it("selects a conversation on click", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByText("Runbook lookup"));
    expect(props.onSelectSession).toHaveBeenCalledWith("s2");
  });

  it("creates a new chat", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /new chat/i }));
    expect(props.onNewChat).toHaveBeenCalled();
  });
});

describe("Sidebar search", () => {
  it("filters conversations by title", async () => {
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByLabelText("Search conversations"), "claims");
    expect(screen.getByText("Claims triage")).toBeInTheDocument();
    expect(screen.queryByText("Runbook lookup")).not.toBeInTheDocument();
  });

  it("shows an empty-state message when nothing matches", async () => {
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByLabelText("Search conversations"), "zzz-nope");
    expect(screen.getByText(/No conversations match/i)).toBeInTheDocument();
  });
});

describe("Sidebar inline rename", () => {
  it("commits a rename on Enter", async () => {
    const user = userEvent.setup();
    const props = setup();

    const row = screen.getByText("Claims triage").closest("div.group") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Rename conversation" }));
    const input = screen.getByLabelText("Conversation title");
    await user.clear(input);
    await user.type(input, "Escalation notes{Enter}");

    expect(props.onRenameSession).toHaveBeenCalledWith("s1", "Escalation notes");
  });

  it("cancels a rename on Escape without calling the handler", async () => {
    const user = userEvent.setup();
    const props = setup();

    const row = screen.getByText("Claims triage").closest("div.group") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Rename conversation" }));
    const input = screen.getByLabelText("Conversation title");
    await user.clear(input);
    await user.type(input, "Discarded{Escape}");

    expect(props.onRenameSession).not.toHaveBeenCalled();
    // Back to display mode showing the original title.
    expect(screen.getByText("Claims triage")).toBeInTheDocument();
  });
});

describe("Sidebar delete", () => {
  it("deletes a conversation via its trash button", async () => {
    const user = userEvent.setup();
    const props = setup();

    const firstRow = screen.getByText("Claims triage").closest("div.group")!;
    await user.click(
      within(firstRow as HTMLElement).getByRole("button", {
        name: "Delete conversation",
      }),
    );
    expect(props.onDeleteSession).toHaveBeenCalledWith("s1");
  });
});
