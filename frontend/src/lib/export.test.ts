import { describe, it, expect } from "vitest";
import { conversationToMarkdown, slugifyTitle } from "./export";
import type { ChatMessage } from "./types";

const ts = new Date("2026-01-01T00:00:00Z");

describe("slugifyTitle", () => {
  it("lowercases and hyphenates", () => {
    expect(slugifyTitle("CFT303E Investigation")).toBe("cft303e-investigation");
  });

  it("strips punctuation and collapses separators", () => {
    expect(slugifyTitle("  How many claims?? (pending)  ")).toBe(
      "how-many-claims-pending",
    );
  });

  it("falls back to 'conversation' for an empty/symbol-only title", () => {
    expect(slugifyTitle("")).toBe("conversation");
    expect(slugifyTitle("!!!")).toBe("conversation");
  });
});

describe("conversationToMarkdown", () => {
  it("renders a titled transcript with You/Assistant headings", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "How do I restart CFT303A?", timestamp: ts },
      { id: "2", role: "assistant", content: "Follow the recovery runbook.", timestamp: ts },
    ];

    const md = conversationToMarkdown(messages, "Job recovery");

    expect(md).toContain("# Job recovery");
    expect(md).toContain("## You");
    expect(md).toContain("How do I restart CFT303A?");
    expect(md).toContain("## Assistant");
    expect(md).toContain("Follow the recovery runbook.");
    expect(md.endsWith("\n")).toBe(true);
  });

  it("includes a Sources section when a message has citations", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "assistant",
        content: "See the runbook.",
        timestamp: ts,
        citations: [
          {
            index: 1,
            source_file: "runbook.pdf",
            section: "Recovery",
            job_id: "CFT303A",
            page_number: 4,
            score: 0.9,
            snippet: "restart the job",
          },
        ],
      },
    ];

    const md = conversationToMarkdown(messages);

    expect(md).toContain("**Sources:**");
    expect(md).toContain("- [1] runbook.pdf — Recovery (p. 4)");
  });

  it("uses a default title and marks empty content", () => {
    const md = conversationToMarkdown([
      { id: "1", role: "assistant", content: "   ", timestamp: ts },
    ]);
    expect(md).toContain("# Conversation");
    expect(md).toContain("_(no content)_");
  });
});
