"use client";

import { useState, useCallback } from "react";
import type { ChatMessage, Citation, PendingAction, ActionResult } from "@/lib/types";
import { api } from "@/lib/api";
import { TOOL_TO_ACTION_TYPE } from "@/lib/constants";

interface UseChatReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  approveAction: (messageId: string, approved: boolean) => Promise<void>;
  clearError: () => void;
  setMessages: (msgs: ChatMessage[]) => void;
}

export function useChat(sessionId: string): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      // Append user message immediately (optimistic)
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const res = await api.chat(content, sessionId);

        // Build assistant message
        const citations: Citation[] | undefined =
          res.citations && res.citations.length > 0 ? res.citations : undefined;

        const pendingAction: PendingAction | undefined =
          res.pending_action ? res.pending_action : undefined;

        const assistantMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.response,
          timestamp: new Date(),
          citations,
          pendingAction,
        };

        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Failed to send message";
        setError(errorMessage);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId],
  );

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
    error,
    sendMessage,
    approveAction,
    clearError,
    setMessages,
  };
}
