"use client";

import { Stethoscope } from "lucide-react";

export function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
        <Stethoscope className="w-4 h-4 text-primary" />
      </div>
      <div className="bg-muted rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-muted-foreground/50 typing-dot" />
          <div className="w-2 h-2 rounded-full bg-muted-foreground/50 typing-dot" />
          <div className="w-2 h-2 rounded-full bg-muted-foreground/50 typing-dot" />
        </div>
      </div>
    </div>
  );
}
