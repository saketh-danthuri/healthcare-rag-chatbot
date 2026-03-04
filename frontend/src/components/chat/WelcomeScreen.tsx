"use client";

import {
  AlertTriangle,
  FileText,
  Database,
  BookOpen,
  Stethoscope,
} from "lucide-react";
import { SUGGESTED_QUESTIONS } from "@/lib/constants";

const iconMap = {
  AlertTriangle,
  FileText,
  Database,
  BookOpen,
};

interface WelcomeScreenProps {
  onSuggestionClick: (question: string) => void;
}

export function WelcomeScreen({ onSuggestionClick }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 py-12">
      {/* Logo */}
      <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-6">
        <Stethoscope className="w-8 h-8 text-primary" />
      </div>

      {/* Title */}
      <h2 className="text-2xl font-semibold mb-2">Healthcare Ops AI Assistant</h2>
      <p className="text-muted-foreground text-center max-w-md mb-8">
        I can help you troubleshoot job failures, find runbook procedures,
        query claims data, and escalate issues. What can I help you with?
      </p>

      {/* Suggested Questions */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
        {SUGGESTED_QUESTIONS.map((item, i) => {
          const Icon = iconMap[item.icon as keyof typeof iconMap];
          return (
            <button
              key={i}
              onClick={() => onSuggestionClick(item.question)}
              className="flex items-start gap-3 p-4 rounded-xl border bg-card hover:bg-accent/50 transition-colors text-left cursor-pointer"
            >
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                <Icon className="w-4 h-4 text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium mb-0.5">{item.title}</p>
                <p className="text-xs text-muted-foreground">{item.question}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
