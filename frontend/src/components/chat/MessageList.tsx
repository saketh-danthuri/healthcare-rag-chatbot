"use client";

import { ArrowDown } from "lucide-react";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import type { ChatMessage, Citation } from "@/lib/types";
import { useAutoScroll } from "@/hooks/useAutoScroll";

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onCitationClick: (citations: Citation[]) => void;
  onApproveAction: (messageId: string, approved: boolean) => void;
  onRegenerate?: () => void;
}

export function MessageList({
  messages,
  isLoading,
  onCitationClick,
  onApproveAction,
  onRegenerate,
}: MessageListProps) {
  const { scrollRef, isAtBottom, scrollToBottom, handleScroll } = useAutoScroll(
    messages.length + (isLoading ? 1 : 0),
  );

  // Index of the last assistant message — the only one that can be regenerated.
  let lastAssistantIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      lastAssistantIdx = i;
      break;
    }
  }

  return (
    <div className="relative flex-1 min-h-0">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto"
      >
        <div className="max-w-3xl mx-auto py-4">
          {messages.map((msg, i) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onCitationClick={onCitationClick}
              onApproveAction={onApproveAction}
              onRegenerate={
                i === lastAssistantIdx && !isLoading ? onRegenerate : undefined
              }
            />
          ))}
          {isLoading && <TypingIndicator />}
        </div>
      </div>

      {/* Jump-to-latest — only when the user has scrolled up */}
      {!isAtBottom && (
        <button
          type="button"
          onClick={() => scrollToBottom()}
          aria-label="Scroll to latest message"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center justify-center w-9 h-9 rounded-full bg-card border shadow-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <ArrowDown className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
