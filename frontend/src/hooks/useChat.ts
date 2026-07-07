"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage, ActionResult } from "@/lib/types";
import { api } from "@/lib/api";
import { getRole } from "@/lib/role";
import { TOOL_TO_ACTION_TYPE } from "@/lib/constants";

interface UseChatReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  /** True for the whole generation (pre-stream wait + token streaming). */
  isStreaming: boolean;
  error: string | null;
  sendMessage: (content: string, fileId?: string, filename?: string) => Promise<void>;
  regenerate: () => Promise<void>;
  stopGeneration: () => void;
  approveAction: (messageId: string, approved: boolean) => Promise<void>;
  clearError: () => void;
  setMessages: (msgs: ChatMessage[]) => void;
}

export function useChat(sessionId: string): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Holds the in-flight stream's controller so the user can stop generation.
  const abortRef = useRef<AbortController | null>(null);

  // Streams a response into an already-appended assistant placeholder. Shared
  // by both a fresh send and a regenerate so the streaming logic lives once.
  const streamInto = useCallback(
    async (assistantId: string, content: string, fileId?: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsLoading(true);
      setIsStreaming(true);
      setError(null);

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));

      try {
        await api.chatStream(
          content,
          sessionId,
          fileId,
          getRole(),
          {
            // Once the stream starts, the streaming bubble replaces the typing
            // indicator, so drop the global loading flag.
            onStart: () => setIsLoading(false),
            onDelta: (e) =>
              patch((m) => ({ ...m, content: m.content + e.text })),
            onFinal: (e) =>
              patch((m) => ({
                ...m,
                content: e.response || m.content,
                citations:
                  e.citations && e.citations.length > 0 ? e.citations : undefined,
                pendingAction: e.pending_action ?? undefined,
                unverifiedCitations:
                  e.unverified_citations && e.unverified_citations.length > 0
                    ? e.unverified_citations
                    : undefined,
                isStreaming: false,
              })),
            onError: (detail) => {
              setError(detail);
              patch((m) => ({ ...m, isStreaming: false }));
            },
          },
          controller.signal,
        );
      } catch (err) {
        // A user-triggered stop aborts the fetch — that is not an error, so we
        // keep whatever streamed so far and simply drop the streaming state.
        if (!controller.signal.aborted) {
          const errorMessage =
            err instanceof Error ? err.message : "Failed to send message";
          setError(errorMessage);
        }
        // Drop the streaming flag; remove the placeholder only if still empty
        // (e.g. a guardrail BLOCK, or a stop before any token arrived).
        setMessages((prev) =>
          prev
            .map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false } : m,
            )
            .filter((m) => !(m.id === assistantId && !m.content)),
        );
      } finally {
        abortRef.current = null;
        setIsLoading(false);
        setIsStreaming(false);
      }
    },
    [sessionId],
  );

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const sendMessage = useCallback(
    async (content: string, fileId?: string, filename?: string) => {
      // Append user message immediately (optimistic)
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: new Date(),
        attachedFile: fileId && filename ? { file_id: fileId, filename } : undefined,
      };

      // Append an assistant placeholder we progressively fill as tokens stream.
      const assistantId = crypto.randomUUID();
      const assistantPlaceholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isStreaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
      await streamInto(assistantId, content, fileId);
    },
    [streamInto],
  );

  // Re-runs the most recent user turn: drops everything after it (the previous
  // assistant answer) and streams a fresh response in its place.
  const regenerate = useCallback(async () => {
    if (isLoading || isStreaming) return;

    let lastUserIdx = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;

    const userMsg = messages[lastUserIdx];
    const assistantId = crypto.randomUUID();

    setMessages((prev) => [
      ...prev.slice(0, lastUserIdx + 1),
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isStreaming: true,
      },
    ]);

    await streamInto(assistantId, userMsg.content, userMsg.attachedFile?.file_id);
  }, [isLoading, isStreaming, messages, streamInto]);

  const approveAction = useCallback(
    async (messageId: string, approved: boolean) => {
      const msg = messages.find((m) => m.id === messageId);
      if (!msg?.pendingAction) return;

      setIsLoading(true);
      setError(null);

      try {
        const actionType =
          TOOL_TO_ACTION_TYPE[msg.pendingAction.tool_name] ||
          msg.pendingAction.tool_name;

        const res = await api.approveAction({
          session_id: sessionId,
          action_type: actionType,
          approved,
          parameters: msg.pendingAction.arguments as Record<string, unknown>,
        });

        const actionResult: ActionResult = {
          success: res.success,
          message: res.message,
          result: res.result,
        };

        // Update the message: remove pendingAction, add actionResult
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? { ...m, pendingAction: undefined, actionResult }
              : m,
          ),
        );
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Action failed";
        setError(errorMessage);
      } finally {
        setIsLoading(false);
      }
    },
    [messages, sessionId],
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    regenerate,
    stopGeneration,
    approveAction,
    clearError,
    setMessages,
  };
}
