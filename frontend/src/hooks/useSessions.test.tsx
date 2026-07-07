import { describe, it, expect } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useSessions } from "./useSessions";
import { loadSessions } from "@/lib/session";
import type { ChatMessage } from "@/lib/types";

const userMsg = (content: string): ChatMessage => ({
  id: "m-" + content,
  role: "user",
  content,
  timestamp: new Date("2026-01-01T00:00:00Z"),
});

describe("useSessions bootstrap", () => {
  it("creates a default 'New Chat' session on first mount", () => {
    const { result } = renderHook(() => useSessions());
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].title).toBe("New Chat");
    expect(result.current.activeId).toBe(result.current.sessions[0].id);
  });
});

describe("useSessions create / switch / delete", () => {
  it("prepends a new session and makes it active", () => {
    const { result } = renderHook(() => useSessions());
    const firstId = result.current.sessions[0].id;

    act(() => {
      result.current.createSession();
    });

    expect(result.current.sessions).toHaveLength(2);
    expect(result.current.activeId).toBe(result.current.sessions[0].id);
    expect(result.current.sessions[1].id).toBe(firstId);
  });

  it("switchSession changes the active id", () => {
    const { result } = renderHook(() => useSessions());
    const original = result.current.sessions[0].id;
    act(() => {
      result.current.createSession();
    });
    act(() => {
      result.current.switchSession(original);
    });
    expect(result.current.activeId).toBe(original);
  });

  it("deleting the active session activates a remaining one", () => {
    const { result } = renderHook(() => useSessions());
    let secondId = "";
    act(() => {
      secondId = result.current.createSession().id;
    });
    // second is active now; delete it -> first remaining becomes active.
    act(() => {
      result.current.deleteSession(secondId);
    });
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.activeId).toBe(result.current.sessions[0].id);
  });

  it("deleting the last session recreates a fresh 'New Chat'", () => {
    const { result } = renderHook(() => useSessions());
    const onlyId = result.current.sessions[0].id;
    act(() => {
      result.current.deleteSession(onlyId);
    });
    expect(result.current.sessions).toHaveLength(1);
    expect(result.current.sessions[0].id).not.toBe(onlyId);
    expect(result.current.sessions[0].title).toBe("New Chat");
  });
});

describe("useSessions titles", () => {
  it("persistMessages auto-derives the title from the first user message", () => {
    const { result } = renderHook(() => useSessions());
    const id = result.current.sessions[0].id;

    act(() => {
      result.current.persistMessages(id, [userMsg("How many claims are pending today?")]);
    });

    expect(result.current.sessions[0].title).toBe("How many claims are pending today?");
    expect(loadSessions()[0].title).toBe("How many claims are pending today?");
  });

  it("renameSession sets a custom title and persists titleCustom", () => {
    const { result } = renderHook(() => useSessions());
    const id = result.current.sessions[0].id;

    act(() => {
      result.current.renameSession(id, "  Claims triage  ");
    });

    expect(result.current.sessions[0].title).toBe("Claims triage");
    expect(result.current.sessions[0].titleCustom).toBe(true);

    const stored = loadSessions()[0];
    expect(stored.title).toBe("Claims triage");
    expect(stored.titleCustom).toBe(true);
  });

  it("renameSession ignores blank titles", () => {
    const { result } = renderHook(() => useSessions());
    const id = result.current.sessions[0].id;
    act(() => {
      result.current.renameSession(id, "   ");
    });
    expect(result.current.sessions[0].title).toBe("New Chat");
    expect(result.current.sessions[0].titleCustom).toBeUndefined();
  });

  it("REGRESSION: a manual rename is never clobbered by auto-derivation", () => {
    const { result } = renderHook(() => useSessions());
    const id = result.current.sessions[0].id;

    act(() => {
      result.current.renameSession(id, "My custom name");
    });
    // A later message would normally re-derive the title — it must not here.
    act(() => {
      result.current.persistMessages(id, [userMsg("A brand new first question")]);
    });

    expect(result.current.sessions[0].title).toBe("My custom name");
    const stored = loadSessions()[0];
    expect(stored.title).toBe("My custom name");
    expect(stored.titleCustom).toBe(true);
  });
});
