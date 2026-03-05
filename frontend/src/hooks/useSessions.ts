"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { ChatSession, ChatMessage } from "@/lib/types";
import {
  generateSessionId,
  deriveSessionTitle,
  loadSessions,
  saveSessions,
  getActiveSessionId,
  setActiveSessionId,
} from "@/lib/session";

interface UseSessionsReturn {
  sessions: ChatSession[];
  activeId: string | null;
  activeSession: ChatSession | null;
  createSession: () => ChatSession;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  /** Save messages to localStorage directly (no React state loop). */
  persistMessages: (sessionId: string, messages: ChatMessage[]) => void;
}

export function useSessions(): UseSessionsReturn {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const sessionsRef = useRef(sessions);
  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  // Load from localStorage on mount
  useEffect(() => {
    const loaded = loadSessions();
    if (loaded.length > 0) {
      setSessions(loaded);
      const savedActiveId = getActiveSessionId();
      const exists = loaded.some((s) => s.id === savedActiveId);
      setActiveId(exists ? savedActiveId : loaded[0].id);
    } else {
      const newSession: ChatSession = {
        id: generateSessionId(),
        title: "New Chat",
        createdAt: new Date(),
        messages: [],
      };
      setSessions([newSession]);
      setActiveId(newSession.id);
    }
  }, []);

  // Persist sessions to localStorage when sessions state changes
  // (only triggered by create/delete/title updates)
  // IMPORTANT: Merge with existing localStorage to preserve messages
  // (React state does NOT hold messages — only persistMessages writes them)
  useEffect(() => {
    if (sessions.length > 0) {
      const stored = loadSessions();
      const storedMap = new Map(stored.map((s) => [s.id, s]));
      const merged = sessions.map((s) => {
        const existing = storedMap.get(s.id);
        return existing
          ? { ...existing, title: s.title, createdAt: s.createdAt }
          : s;
      });
      saveSessions(merged);
    }
  }, [sessions]);

  useEffect(() => {
    if (activeId) {
      setActiveSessionId(activeId);
    }
  }, [activeId]);

  const activeSession = sessions.find((s) => s.id === activeId) || null;

  const createSession = useCallback(() => {
    const newSession: ChatSession = {
      id: generateSessionId(),
      title: "New Chat",
      createdAt: new Date(),
      messages: [],
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveId(newSession.id);
    return newSession;
  }, []);

  const switchSession = useCallback((id: string) => {
    setActiveId(id);
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const filtered = prev.filter((s) => s.id !== id);
        if (filtered.length === 0) {
          const newSession: ChatSession = {
            id: generateSessionId(),
            title: "New Chat",
            createdAt: new Date(),
            messages: [],
          };
          setActiveId(newSession.id);
          return [newSession];
        }
        if (activeId === id) {
          setActiveId(filtered[0].id);
        }
        return filtered;
      });
    },
    [activeId],
  );

  /**
   * Persist messages to localStorage directly - bypasses React state
   * to avoid the infinite re-render loop.
   * Also updates the sidebar title in React state (only the title, not messages).
   */
  const lastPersistedTitleRef = useRef<Record<string, string>>({});

  const persistMessages = useCallback(
    (sessionId: string, messages: ChatMessage[]) => {
      // 1. Save full messages to localStorage directly
      const stored = loadSessions();
      const firstUserMsg = messages.find((m) => m.role === "user");
      const newTitle = firstUserMsg
        ? deriveSessionTitle(firstUserMsg.content)
        : undefined;

      const updated = stored.map((s) => {
        if (s.id !== sessionId) return s;
        return { ...s, messages, title: newTitle || s.title };
      });
      saveSessions(updated);

      // 2. Update ONLY the title in React state IF it actually changed
      //    Use a ref to track what we've already set, avoiding unnecessary setSessions calls
      if (newTitle && lastPersistedTitleRef.current[sessionId] !== newTitle) {
        lastPersistedTitleRef.current[sessionId] = newTitle;
        setSessions((prev) => {
          const idx = prev.findIndex((s) => s.id === sessionId);
          if (idx === -1 || prev[idx].title === newTitle) return prev; // return SAME reference
          const copy = [...prev];
          copy[idx] = { ...copy[idx], title: newTitle };
          return copy;
        });
      }
    },
    [],
  );

  return {
    sessions,
    activeId,
    activeSession,
    createSession,
    switchSession,
    deleteSession,
    persistMessages,
  };
}
