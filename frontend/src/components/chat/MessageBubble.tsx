"use client";

import { User, Stethoscope } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { ActionApprovalCard } from "@/components/actions/ActionApprovalCard";
import { ActionResultCard } from "@/components/actions/ActionResultCard";
import type { ChatMessage, Citation } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

interface MessageBubbleProps {
  message: ChatMessage;
  onCitationClick?: (citations: Citation[]) => void;
  onApproveAction?: (messageId: string, approved: boolean) => void;
}

export function MessageBubble({
  message,
  onCitationClick,
  onApproveAction,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 ${
        isUser ? "flex-row-reverse" : ""
      }`}
    >
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-primary/10"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : (
          <Stethoscope className="w-4 h-4 text-primary" />
        )}
      </div>

      {/* Message content */}
      <div
        className={`max-w-[80%] space-y-1 ${isUser ? "items-end" : "items-start"}`}
      >
        {/* Bubble */}
        <div
          className={
            isUser
              ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5"
              : "bg-muted rounded-2xl rounded-tl-sm px-4 py-3"
          }
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="markdown-content text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Citation badges */}
        {message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {message.citations.map((c) => (
              <Badge
                key={c.index}
                variant="citation"
                className="text-xs cursor-pointer"
                onClick={() => onCitationClick?.(message.citations!)}
              >
                [{c.index}] {c.source_file.length > 20 ? c.source_file.slice(0, 20) + "..." : c.source_file}
              </Badge>
            ))}
          </div>
        )}

        {/* Pending Action */}
        {message.pendingAction && onApproveAction && (
          <ActionApprovalCard
            action={message.pendingAction}
            onApprove={() => onApproveAction(message.id, true)}
            onReject={() => onApproveAction(message.id, false)}
          />
        )}

        {/* Action Result */}
        {message.actionResult && (
          <ActionResultCard result={message.actionResult} />
        )}

        {/* Timestamp */}
        <p
          className={`text-xs text-muted-foreground mt-1 ${
            isUser ? "text-right" : "text-left"
          }`}
        >
          {formatTimestamp(message.timestamp)}
        </p>
      </div>
    </div>
  );
}
