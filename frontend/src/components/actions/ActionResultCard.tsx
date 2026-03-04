"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { ActionResult } from "@/lib/types";

interface ActionResultCardProps {
  result: ActionResult;
}

export function ActionResultCard({ result }: ActionResultCardProps) {
  return (
    <Card
      className={`mt-3 ${
        result.success
          ? "border-success/50 bg-success/5"
          : "border-destructive/50 bg-destructive/5"
      }`}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-2">
          {result.success ? (
            <CheckCircle2 className="w-4 h-4 text-success mt-0.5 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
          )}
          <div>
            <p className="text-sm font-medium">
              {result.success ? "Action Completed" : "Action Failed"}
            </p>
            <p className="text-sm text-muted-foreground mt-0.5">
              {result.message}
            </p>
            {result.result && Object.keys(result.result).length > 0 && (
              <pre className="mt-2 text-xs bg-muted p-2 rounded overflow-x-auto">
                {JSON.stringify(result.result, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
