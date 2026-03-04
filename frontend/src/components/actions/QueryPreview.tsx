"use client";

import { Database } from "lucide-react";

interface QueryPreviewProps {
  arguments: Record<string, unknown>;
}

export function QueryPreview({ arguments: args }: QueryPreviewProps) {
  const description = args.description ? String(args.description) : null;
  const sqlQuery = args.sql_query ? String(args.sql_query) : null;

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Database className="w-4 h-4" />
        <span className="font-medium">Database Query</span>
      </div>
      <div className="bg-muted/50 rounded-lg p-3 space-y-2">
        {description && (
          <div>
            <span className="text-xs font-medium text-muted-foreground">Description:</span>
            <p className="text-sm">{description}</p>
          </div>
        )}
        {sqlQuery && (
          <div>
            <span className="text-xs font-medium text-muted-foreground">SQL Query:</span>
            <pre className="mt-1 bg-muted rounded p-2 text-xs font-mono overflow-x-auto">
              {sqlQuery}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
