"use client";

import { BookOpen } from "lucide-react";

interface ConfluencePreviewProps {
  arguments: Record<string, unknown>;
}

function Field({ label, value }: { label: string; value: unknown }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="text-sm whitespace-pre-wrap">{String(value)}</div>
    </div>
  );
}

export function ConfluencePreview({ arguments: args }: ConfluencePreviewProps) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <BookOpen className="w-4 h-4" />
        <span className="font-medium">Confluence Page Preview</span>
      </div>
      <div className="bg-muted/50 rounded-lg p-3 space-y-3">
        <Field label="Title:" value={args.title} />
        <Field label="Space:" value={args.space_key || "(default)"} />
        <Field label="Summary:" value={args.summary} />
        <Field label="Key Decisions:" value={args.key_decisions} />
        <Field label="Action Items:" value={args.action_items} />
        <Field label="Attendees:" value={args.attendees} />
      </div>
    </div>
  );
}
