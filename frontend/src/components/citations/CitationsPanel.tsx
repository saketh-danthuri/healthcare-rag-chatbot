"use client";

import { X, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CitationCard } from "./CitationCard";
import type { Citation } from "@/lib/types";

interface CitationsPanelProps {
  citations: Citation[];
  isOpen: boolean;
  onClose: () => void;
  selectedIndex?: number;
  onSelectCitation?: (index: number) => void;
}

export function CitationsPanel({
  citations,
  isOpen,
  onClose,
  selectedIndex,
  onSelectCitation,
}: CitationsPanelProps) {
  if (!isOpen || citations.length === 0) return null;

  return (
    <aside className="w-[320px] border-l bg-card flex flex-col h-full shrink-0">
      {/* Header */}
      <div className="h-14 border-b flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-primary" />
          <h2 className="font-semibold text-sm">
            Sources ({citations.length})
          </h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8">
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Citation cards */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {citations.map((citation) => (
          <CitationCard
            key={citation.index}
            citation={citation}
            isSelected={selectedIndex === citation.index}
            onClick={() => onSelectCitation?.(citation.index)}
          />
        ))}
      </div>
    </aside>
  );
}
