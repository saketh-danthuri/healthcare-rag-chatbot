/* ============================================================
   Session management - generates IDs, persists to localStorage.
   ============================================================ */

import type { ChatSession, ChatMessage } from "./types";

const SESSIONS_KEY = "healthcare-chatbot-sessions";
const ACTIVE_SESSION_KEY = "healthcare-chatbot-active-session";

export function generateSessionId(): string {
  return `session-${crypto.randomUUID()}`;
}

export function deriveSessionTitle(firstMessage: string): string {
  const trimmed = firstMessage.trim();
  if (trimmed.length <= 45) return trimmed;
  return trimmed.slice(0, 45) + "...";
}

// --- localStorage helpers ---

export function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Array<{
      id: string;
      title: string;
      createdAt: string;
      messages: Array<ChatMessage & { timestamp: string }>;
    }>;
    return parsed.map((s) => ({
      ...s,
      createdAt: new Date(s.createdAt),
      messages: s.messages.map((m) => ({
        ...m,
        timestamp: new Date(m.timestamp),
      })),
    }));
  } catch {
    return [];
  }
}

export function saveSessions(sessions: ChatSession[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  } catch {
    // localStorage full or unavailable
  }
}

export function getActiveSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACTIVE_SESSION_KEY);
}

export function setActiveSessionId(id: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACTIVE_SESSION_KEY, id);
}
