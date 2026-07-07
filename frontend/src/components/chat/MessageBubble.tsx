"use client";

import { User, Stethoscope, AlertTriangle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Badge } from "@/components/ui/badge";
import { ActionApprovalCard } from "@/components/actions/ActionApprovalCard";
import { ActionResultCard } from "@/components/actions/ActionResultCard";
import { MessageActions } from "./MessageActions";
import type { ChatMessage, Citation } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

interface MessageBubbleProps {
  message: ChatMessage;
  onCitationClick?: (citations: Citation[]) => void;
  onApproveAction?: (messageId: string, approved: boolean) => void;
  /** Show a regenerate control (only for the latest assistant message). */
  onRegenerate?: () => void;
}

export function MessageBubble({
  message,
  onCitationClick,
  onApproveAction,
  onRegenerate,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`group flex items-start gap-3 px-4 py-3 ${
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
              {message.content && (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              )}
              {message.isStreaming && (
                <span
                  className="inline-block w-1.5 h-4 -mb-0.5 bg-primary/70 animate-pulse"
                  aria-label="Streaming response"
                />
              )}
            </div>
          )}
        </div>

        {/* Unverified citation warnings: [Source N] the answer cited but that
            was NOT retrieved (potential hallucinated reference). */}
        {message.unverifiedCitations && message.unverifiedCitations.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {message.unverifiedCitations.map((n) => (
              <Badge
                key={n}
                variant="destructive"
                className="text-xs gap-1"
                title="This source was cited in the answer but was not among the retrieved documents."
              >
                <AlertTriangle className="w-3 h-3" />
                Unverified [Source {n}]
              </Badge>
            ))}
          </div>
        )}

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

        {/* Timestamp + hover actions */}
        <div
          className={`flex items-center gap-2 mt-1 ${
            isUser ? "flex-row-reverse" : "flex-row"
          }`}
        >
          <p className="text-xs text-muted-foreground">
            {formatTimestamp(message.timestamp)}
          </p>
          {!message.isStreaming && !message.pendingAction && (
            <MessageActions
              content={message.content}
              align={isUser ? "right" : "left"}
              onRegenerate={!isUser ? onRegenerate : undefined}
            />
          )}
        </div>
      </div>
    </div>
  );
}
