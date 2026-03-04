"use client";

import { ShieldAlert, Check, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmailPreview } from "./EmailPreview";
import { QueryPreview } from "./QueryPreview";
import type { PendingAction } from "@/lib/types";
import { ACTION_TYPE_LABELS } from "@/lib/constants";
import { useState } from "react";

interface ActionApprovalCardProps {
  action: PendingAction;
  onApprove: () => void;
  onReject: () => void;
}

export function ActionApprovalCard({
  action,
  onApprove,
  onReject,
}: ActionApprovalCardProps) {
  const [isProcessing, setIsProcessing] = useState(false);

  const handleApprove = async () => {
    setIsProcessing(true);
    onApprove();
  };

  const handleReject = async () => {
    setIsProcessing(true);
    onReject();
  };

  const actionLabel =
    ACTION_TYPE_LABELS[action.tool_name] || action.tool_name;

  return (
    <Card className="border-warning/50 bg-warning/5 mt-3">
      <CardContent className="p-4 space-y-3">
        {/* Warning header */}
        <div className="flex items-center gap-2 text-warning">
          <ShieldAlert className="w-4 h-4" />
          <span className="text-sm font-semibold">Action Requires Approval</span>
        </div>

        {/* Action label */}
        <p className="text-sm font-medium">{actionLabel}</p>

        {/* Action-specific preview */}
        {action.tool_name === "send_escalation_email" ? (
          <EmailPreview arguments={action.arguments} />
        ) : action.tool_name === "query_database" ? (
          <QueryPreview arguments={action.arguments} />
        ) : (
          <pre className="text-xs bg-muted p-2 rounded overflow-x-auto">
            {JSON.stringify(action.arguments, null, 2)}
          </pre>
        )}

        {/* Approve / Reject buttons */}
        <div className="flex items-center gap-2 pt-1">
          <Button
            size="sm"
            variant="success"
            onClick={handleApprove}
            disabled={isProcessing}
            className="gap-1.5"
          >
            {isProcessing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Check className="w-3.5 h-3.5" />
            )}
            Approve
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={handleReject}
            disabled={isProcessing}
            className="gap-1.5"
          >
            <X className="w-3.5 h-3.5" />
            Reject
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
