import { describe, it, expect } from "vitest";
import { getRole, setRole, getUserId } from "./role";

describe("getRole", () => {
  it("defaults to the most restrictive 'general' when unset", () => {
    expect(getRole()).toBe("general");
  });

  it("returns a stored valid role", () => {
    setRole("clinician");
    expect(getRole()).toBe("clinician");
    setRole("general");
    expect(getRole()).toBe("general");
  });

  it("falls back to 'general' for a garbage stored value", () => {
    localStorage.setItem("user-role", "admin-hacker");
    expect(getRole()).toBe("general");
  });
});

describe("getUserId", () => {
  it("mints a stable per-browser id and reuses it", () => {
    const first = getUserId();
    expect(first).toMatch(/^user-/);
    const second = getUserId();
    expect(second).toBe(first);
    expect(localStorage.getItem("user-id")).toBe(first);
  });
});
