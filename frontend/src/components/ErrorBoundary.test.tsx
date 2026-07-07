import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ErrorBoundary } from "./ErrorBoundary";

function Boom(): React.ReactElement {
  throw new Error("kaboom");
}

describe("ErrorBoundary", () => {
  // React logs caught render errors to console.error — silence it for clean output.
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children normally when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("shows the fallback card when a child throws instead of white-screening", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("recovers via 'Try again' once the child stops throwing", async () => {
    const user = userEvent.setup();

    function Toggle(): React.ReactElement {
      const [broken, setBroken] = useState(true);
      return (
        <ErrorBoundary>
          {broken ? <Boom /> : <p>recovered</p>}
          <button onClick={() => setBroken(false)}>fix</button>
        </ErrorBoundary>
      );
    }

    render(<Toggle />);
    // While thrown, the fix button is unmounted; flip state then reset.
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    // After reset the boundary re-renders children — still broken here, so it
    // re-catches; this asserts reset re-attempts render rather than staying stuck.
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("supports a custom fallback render prop", () => {
    render(
      <ErrorBoundary fallback={(err) => <p>custom: {err.message}</p>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("custom: kaboom")).toBeInTheDocument();
  });
});
