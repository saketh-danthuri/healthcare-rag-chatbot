import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom does not implement scrollIntoView; several components call it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// crypto.randomUUID exists in Node 20+, but guard for older jsdom globals.
if (typeof globalThis.crypto?.randomUUID !== "function") {
  let counter = 0;
  Object.defineProperty(globalThis, "crypto", {
    value: {
      ...globalThis.crypto,
      randomUUID: () =>
        `00000000-0000-4000-8000-${String(counter++).padStart(12, "0")}`,
    },
    configurable: true,
  });
}

// Each test starts from a clean DOM + empty localStorage so persistence tests
// never leak state into one another.
beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});
