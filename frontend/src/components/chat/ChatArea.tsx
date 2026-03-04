"use client";

import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { WelcomeScreen } from "./WelcomeScreen";
import type { ChatMessage, Citation } from "@/lib/types";

interface ChatAreaProps {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  onSendMessage: (message: string) => void;
  onCitationClick: (citations: Citation[]) => void;
  onApproveAction: (messageId: string, approved: boolean) => void;
}

export function ChatArea({
  messages,
  isLoading,
  error,
  onSendMessage,
  onCitationClick,
  onApproveAction,
}: ChatAreaProps) {
  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Error banner */}
      {error && (
        <div className="bg-destructive/10 border-b border-destructive/20 px-4 py-2">
          <p className="text-sm text-destructive text-center">{error}</p>
        </div>
      )}

      {/* Messages or Welcome */}
      {messages.length === 0 ? (
        <WelcomeScreen onSuggestionClick={onSendMessage} />
      ) : (
        <MessageList
          messages={messages}
          isLoading={isLoading}
          onCitationClick={onCitationClick}
          onApproveAction={onApproveAction}
        />
      )}

      {/* Input */}
      <ChatInput onSend={onSendMessage} isLoading={isLoading} />
    </div>
  );
}
