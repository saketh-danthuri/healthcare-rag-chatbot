import { describe, it, expect } from "vitest";
import { truncate, formatTimestamp, cn } from "./utils";

describe("truncate", () => {
  it("returns strings at or below the limit unchanged (boundary)", () => {
    expect(truncate("hello", 5)).toBe("hello");
    expect(truncate("hi", 5)).toBe("hi");
  });

  it("adds an ellipsis once the limit is exceeded", () => {
    expect(truncate("hello world", 5)).toBe("hello...");
  });
});

describe("formatTimestamp", () => {
  it("formats a Date as a 12-hour clock string", () => {
    const out = formatTimestamp(new Date("2026-01-01T13:05:00"));
    expect(out).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });
});

describe("cn", () => {
  it("merges conflicting tailwind classes, last wins", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("drops falsy values", () => {
    expect(cn("a", false && "b", undefined, "c")).toBe("a c");
  });
});
