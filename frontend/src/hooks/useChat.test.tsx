import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { StreamHandlers } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";
import { useChat } from "./useChat";

// Mock the whole API layer — we drive the streaming handlers by hand so the
// tests are deterministic and never touch the network.
vi.mock("@/lib/api", () => ({
  api: {
    chatStream: vi.fn(),
    approveAction: vi.fn(),
    uploadFile: vi.fn(),
  },
}));

import { api } from "@/lib/api";

const chatStream = api.chatStream as unknown as ReturnType<typeof vi.fn>;
const approveAction = api.approveAction as unknown as ReturnType<typeof vi.fn>;

type StreamArgs = [
  string,
  string,
  string | undefined,
  string,
  StreamHandlers,
  AbortSignal | undefined,
];

beforeEach(() => {
  chatStream.mockReset();
  approveAction.mockReset();
});

describe("useChat.sendMessage", () => {
  it("appends the user turn, streams deltas, then applies the final payload", async () => {
    chatStream.mockImplementation(
      async (...args: StreamArgs) => {
        const handlers = args[4];
        handlers.onStart?.("general");
        handlers.onDelta?.({ type: "delta", text: "Restart " });
        handlers.onDelta?.({ type: "delta", text: "the job." });
        handlers.onFinal?.({
          type: "final",
          session_id: "s1",
          response: "Restart the job.",
          citations: [
            {
              index: 1,
              source_file: "runbook.pdf",
              section: "Recovery",
              job_id: "CFT303A",
              page_number: 2,
              score: 0.9,
              snippet: "restart",
            },
          ],
          unverified_citations: [],
          pending_action: null,
        });
      },
    );

    const { result } = renderHook(() => useChat("s1"));

    await act(async () => {
      await result.current.sendMessage("How do I restart CFT303A?");
    });

    const msgs = result.current.messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[0]).toMatchObject({ role: "user", content: "How do I restart CFT303A?" });
    expect(msgs[1]).toMatchObject({
      role: "assistant",
      content: "Restart the job.",
      isStreaming: false,
    });
    expect(msgs[1].citations).toHaveLength(1);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sets an error and removes the empty placeholder when the request throws", async () => {
    chatStream.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useChat("s1"));

    await act(async () => {
      await result.current.sendMessage("hello");
    });

    // Only the user turn survives; the empty assistant placeholder is dropped.
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.error).toBe("network down");
    expect(result.current.isStreaming).toBe(false);
  });

  it("surfaces a guardrail block via onError", async () => {
    chatStream.mockImplementation(async (...args: StreamArgs) => {
      args[4].onError?.("Message blocked by policy");
    });

    const { result } = renderHook(() => useChat("s1"));
    await act(async () => {
      await result.current.sendMessage("something disallowed");
    });

    expect(result.current.error).toBe("Message blocked by policy");
    expect(result.current.isStreaming).toBe(false);
  });
});

describe("useChat.stopGeneration", () => {
  it("keeps partial content and raises no error when aborted mid-stream", async () => {
    // Emits one delta, then hangs until the abort signal fires.
    chatStream.mockImplementation(
      (...args: StreamArgs) =>
        new Promise((_resolve, reject) => {
          const handlers = args[4];
          const signal = args[5];
          handlers.onStart?.("general");
          handlers.onDelta?.({ type: "delta", text: "Partial answer" });
          signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );

    const { result } = renderHook(() => useChat("s1"));

    // Kick off the send but do NOT await — it stays pending until we stop it.
    let sendPromise: Promise<void>;
    act(() => {
      sendPromise = result.current.sendMessage("long question");
    });

    await waitFor(() => expect(result.current.isStreaming).toBe(true));

    await act(async () => {
      result.current.stopGeneration();
      await sendPromise;
    });

    const msgs = result.current.messages;
    expect(msgs).toHaveLength(2);
    // Partial tokens are preserved — a stop is not a discard.
    expect(msgs[1].content).toBe("Partial answer");
    expect(msgs[1].isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });

  it("removes the placeholder if aborted before any token arrived", async () => {
    chatStream.mockImplementation(
      (...args: StreamArgs) =>
        new Promise((_resolve, reject) => {
          args[4].onStart?.("general");
          args[5]?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );

    const { result } = renderHook(() => useChat("s1"));
    let sendPromise: Promise<void>;
    act(() => {
      sendPromise = result.current.sendMessage("q");
    });
    await waitFor(() => expect(result.current.isStreaming).toBe(true));

    await act(async () => {
      result.current.stopGeneration();
      await sendPromise;
    });

    // Empty assistant bubble gone; only the user turn remains.
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.error).toBeNull();
  });
});

describe("useChat.regenerate", () => {
  it("drops the previous answer and re-streams from the last user turn", async () => {
    chatStream.mockImplementation(async (...args: StreamArgs) => {
      args[4].onFinal?.({
        type: "final",
        session_id: "s1",
        response: "First answer",
        citations: [],
        unverified_citations: [],
        pending_action: null,
      });
    });

    const { result } = renderHook(() => useChat("s1"));
    await act(async () => {
      await result.current.sendMessage("the question");
    });
    expect(result.current.messages[1].content).toBe("First answer");

    // Next generation returns a different answer.
    chatStream.mockImplementation(async (...args: StreamArgs) => {
      args[4].onFinal?.({
        type: "final",
        session_id: "s1",
        response: "Second answer",
        citations: [],
        unverified_citations: [],
        pending_action: null,
      });
    });

    await act(async () => {
      await result.current.regenerate();
    });

    const msgs = result.current.messages;
    expect(msgs).toHaveLength(2);
    expect(msgs[0]).toMatchObject({ role: "user", content: "the question" });
    expect(msgs[1].content).toBe("Second answer");
    // Regenerate re-sends the SAME user content.
    const lastCall = chatStream.mock.calls.at(-1) as StreamArgs;
    expect(lastCall[0]).toBe("the question");
  });

  it("is a no-op when there is no user message", async () => {
    const { result } = renderHook(() => useChat("s1"));
    await act(async () => {
      await result.current.regenerate();
    });
    expect(chatStream).not.toHaveBeenCalled();
    expect(result.current.messages).toHaveLength(0);
  });
});

describe("useChat.approveAction", () => {
  it("maps the tool name to an action_type and records the result", async () => {
    approveAction.mockResolvedValue({
      success: true,
      message: "Email sent",
      result: { id: "e1" },
    });

    const { result } = renderHook(() => useChat("s1"));

    const pending: ChatMessage = {
      id: "a1",
      role: "assistant",
      content: "I'll escalate this.",
      timestamp: new Date(),
      pendingAction: {
        tool_name: "send_escalation_email",
        arguments: { to: "oncall@example.com" },
        status: "pending",
      },
    };
    act(() => {
      result.current.setMessages([pending]);
    });

    await act(async () => {
      await result.current.approveAction("a1", true);
    });

    // tool_name send_escalation_email maps to action_type send_email.
    expect(approveAction).toHaveBeenCalledWith(
      expect.objectContaining({
        session_id: "s1",
        action_type: "send_email",
        approved: true,
        parameters: { to: "oncall@example.com" },
      }),
    );

    const msg = result.current.messages[0];
    expect(msg.pendingAction).toBeUndefined();
    expect(msg.actionResult).toMatchObject({ success: true, message: "Email sent" });
  });

  it("does nothing when the message has no pending action", async () => {
    const { result } = renderHook(() => useChat("s1"));
    act(() => {
      result.current.setMessages([
        { id: "x", role: "assistant", content: "hi", timestamp: new Date() },
      ]);
    });
    await act(async () => {
      await result.current.approveAction("x", true);
    });
    expect(approveAction).not.toHaveBeenCalled();
  });
});
