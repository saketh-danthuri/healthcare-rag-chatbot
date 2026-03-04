"use client";

import { Mail } from "lucide-react";

interface EmailPreviewProps {
  arguments: Record<string, unknown>;
}

function Field({ label, value }: { label: string; value: unknown }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <p className="text-sm">{String(value)}</p>
    </div>
  );
}

export function EmailPreview({ arguments: args }: EmailPreviewProps) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Mail className="w-4 h-4" />
        <span className="font-medium">Escalation Email</span>
      </div>
      <div className="bg-muted/50 rounded-lg p-3 space-y-2">
        <Field label="To:" value={args.recipient} />
        <Field label="Subject:" value={args.subject} />
        <Field label="Issue Summary:" value={args.issue_summary} />
        <Field label="Runbook Reference:" value={args.runbook_reference} />
        <Field label="Recommended Action:" value={args.recommended_action} />
      </div>
    </div>
  );
}
