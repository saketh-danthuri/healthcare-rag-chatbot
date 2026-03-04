"use client";

import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import type { ChatMessage, Citation } from "@/lib/types";
import { useAutoScroll } from "@/hooks/useAutoScroll";

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onCitationClick: (citations: Citation[]) => void;
  onApproveAction: (messageId: string, approved: boolean) => void;
}

export function MessageList({
  messages,
  isLoading,
  onCitationClick,
  onApproveAction,
}: MessageListProps) {
  const scrollRef = useAutoScroll(messages.length + (isLoading ? 1 : 0));

  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto py-4">
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onCitationClick={onCitationClick}
            onApproveAction={onApproveAction}
          />
        ))}
        {isLoading && <TypingIndicator />}
      </div>
    </div>
  );
}
