import { describe, it, expect } from "vitest";
import {
  deriveSessionTitle,
  loadSessions,
  saveSessions,
  getActiveSessionId,
  setActiveSessionId,
  generateSessionId,
} from "./session";
import type { ChatSession } from "./types";

describe("deriveSessionTitle", () => {
  it("trims and returns short messages unchanged", () => {
    expect(deriveSessionTitle("  How many claims are pending?  ")).toBe(
      "How many claims are pending?",
    );
  });

  it("returns a 45-char message as-is (boundary, no ellipsis)", () => {
    const exactly45 = "x".repeat(45);
    expect(deriveSessionTitle(exactly45)).toBe(exactly45);
    expect(deriveSessionTitle(exactly45)).not.toContain("...");
  });

  it("truncates a 46-char message to 45 chars + ellipsis (boundary)", () => {
    const result = deriveSessionTitle("y".repeat(46));
    expect(result).toBe("y".repeat(45) + "...");
    expect(result).toHaveLength(48);
  });
});

describe("generateSessionId", () => {
  it("is prefixed and unique across calls", () => {
    const a = generateSessionId();
    const b = generateSessionId();
    expect(a).toMatch(/^session-/);
    expect(a).not.toBe(b);
  });
});

describe("session persistence round-trip", () => {
  const sample: ChatSession[] = [
    {
      id: "session-1",
      title: "Claims triage",
      createdAt: new Date("2026-01-02T03:04:05.000Z"),
      titleCustom: true,
      messages: [
        {
          id: "m1",
          role: "user",
          content: "hi",
          timestamp: new Date("2026-01-02T03:04:06.000Z"),
        },
      ],
    },
  ];

  it("revives Date instances for session and message timestamps", () => {
    saveSessions(sample);
    const loaded = loadSessions();

    expect(loaded).toHaveLength(1);
    expect(loaded[0].createdAt).toBeInstanceOf(Date);
    expect(loaded[0].createdAt.toISOString()).toBe("2026-01-02T03:04:05.000Z");
    expect(loaded[0].messages[0].timestamp).toBeInstanceOf(Date);
    expect(loaded[0].titleCustom).toBe(true);
  });

  it("returns [] when nothing is stored", () => {
    expect(loadSessions()).toEqual([]);
  });

  it("returns [] (never throws) on corrupt JSON", () => {
    localStorage.setItem("healthcare-chatbot-sessions", "{ not json");
    expect(loadSessions()).toEqual([]);
  });
});

describe("active session id", () => {
  it("returns null before anything is set", () => {
    expect(getActiveSessionId()).toBeNull();
  });

  it("round-trips through localStorage", () => {
    setActiveSessionId("session-abc");
    expect(getActiveSessionId()).toBe("session-abc");
  });
});
