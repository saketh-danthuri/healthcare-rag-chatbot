/* ============================================================
   Conversation export — turn the in-memory transcript into a
   downloadable Markdown file. The formatting is a pure function so it
   can be unit-tested without touching the DOM.
   ============================================================ */

import type { ChatMessage } from "./types";

/** Filesystem-safe slug for the download filename. */
export function slugifyTitle(title: string): string {
  const slug = title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "conversation";
}

/** Render a conversation as Markdown, including citations if present. */
export function conversationToMarkdown(
  messages: ChatMessage[],
  title = "Conversation",
): string {
  const lines: string[] = [`# ${title}`, ""];

  for (const m of messages) {
    const who = m.role === "user" ? "You" : "Assistant";
    lines.push(`## ${who}`);
    lines.push("");
    lines.push(m.content.trim() || "_(no content)_");
    lines.push("");

    if (m.citations && m.citations.length > 0) {
      lines.push("**Sources:**");
      for (const c of m.citations) {
        lines.push(
          `- [${c.index}] ${c.source_file} — ${c.section} (p. ${c.page_number})`,
        );
      }
      lines.push("");
    }
  }

  return lines.join("\n").trimEnd() + "\n";
}

/**
 * Trigger a browser download of the conversation as a .md file.
 * No-op when there are no messages.
 */
export function downloadConversation(
  messages: ChatMessage[],
  title = "Conversation",
): void {
  if (typeof window === "undefined" || messages.length === 0) return;

  const markdown = conversationToMarkdown(messages, title);
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slugifyTitle(title)}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
