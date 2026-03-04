"use client";

import { FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

interface CitationCardProps {
  citation: Citation;
  isSelected?: boolean;
  onClick?: () => void;
}

export function CitationCard({ citation, isSelected, onClick }: CitationCardProps) {
  const scorePercent = Math.round(citation.score * 100);
  const scoreColor =
    citation.score >= 0.7
      ? "bg-success"
      : citation.score >= 0.4
        ? "bg-warning"
        : "bg-destructive";

  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md",
        isSelected && "ring-2 ring-primary",
      )}
      onClick={onClick}
    >
      <CardContent className="p-3 space-y-2">
        {/* Header with source index */}
        <div className="flex items-start gap-2">
          <Badge variant="citation" className="shrink-0 text-xs">
            {citation.index}
          </Badge>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
              <p className="text-sm font-medium truncate">
                {citation.source_file}
              </p>
            </div>
          </div>
        </div>

        {/* Metadata */}
        <div className="flex flex-wrap gap-1.5">
          {citation.section && (
            <Badge variant="secondary" className="text-xs">
              {citation.section}
            </Badge>
          )}
          {citation.job_id && (
            <Badge variant="outline" className="text-xs">
              {citation.job_id}
            </Badge>
          )}
          {citation.page_number && (
            <Badge variant="outline" className="text-xs">
              p.{citation.page_number}
            </Badge>
          )}
        </div>

        {/* Relevance score bar */}
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all", scoreColor)}
              style={{ width: `${scorePercent}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-9 text-right">
            {scorePercent}%
          </span>
        </div>

        {/* Snippet */}
        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
          {citation.snippet}
        </p>
      </CardContent>
    </Card>
  );
}
