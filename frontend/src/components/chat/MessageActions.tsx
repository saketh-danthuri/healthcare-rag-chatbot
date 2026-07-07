"use client";

import { useCallback, useState } from "react";
import { Check, Copy, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface MessageActionsProps {
  content: string;
  /** Alignment: user messages sit on the right, assistant on the left. */
  align: "left" | "right";
  /** Only the latest assistant message can be regenerated. */
  onRegenerate?: () => void;
  className?: string;
}

/**
 * Hover-revealed row of per-message actions (copy, regenerate). Kept
 * lightweight and self-contained so it can attach to any message bubble.
 */
export function MessageActions({
  content,
  align,
  onRegenerate,
  className,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable (e.g. insecure context) — fail silently.
    }
  }, [content]);

  if (!content) return null;

  const btn =
    "p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors";

  return (
    <div
      className={cn(
        "flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity",
        align === "right" ? "justify-end" : "justify-start",
        className,
      )}
    >
      <button
        type="button"
        onClick={handleCopy}
        className={btn}
        aria-label={copied ? "Copied" : "Copy message"}
        title={copied ? "Copied" : "Copy"}
      >
        {copied ? (
          <Check className="w-3.5 h-3.5 text-success" />
        ) : (
          <Copy className="w-3.5 h-3.5" />
        )}
      </button>

      {onRegenerate && (
        <button
          type="button"
          onClick={onRegenerate}
          className={btn}
          aria-label="Regenerate response"
          title="Regenerate response"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
