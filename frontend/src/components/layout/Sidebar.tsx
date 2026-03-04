"use client";

import { Plus, MessageSquare, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ChatSession } from "@/lib/types";
import { cn } from "@/lib/utils";
import { formatTimestamp } from "@/lib/utils";

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onClose?: () => void;
  showCloseButton?: boolean;
}

export function Sidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClose,
  showCloseButton,
}: SidebarProps) {
  return (
    <aside className="w-[280px] bg-sidebar text-sidebar-foreground border-r border-sidebar-border flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-sidebar-border flex items-center justify-between">
        <Button
          onClick={onNewChat}
          variant="outline"
          size="sm"
          className="flex-1 justify-start gap-2"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </Button>
        {showCloseButton && (
          <Button variant="ghost" size="icon" onClick={onClose} className="ml-2">
            <X className="w-4 h-4" />
          </Button>
        )}
      </div>

      {/* Session List */}
      <div className="flex-1 overflow-y-auto py-2">
        {sessions.length === 0 ? (
          <p className="text-xs text-muted-foreground px-3 py-4">
            No conversations yet. Start a new chat!
          </p>
        ) : (
          sessions.map((session) => (
            <div
              key={session.id}
              className={cn(
                "group flex items-center gap-2 px-3 py-2.5 mx-2 rounded-lg cursor-pointer transition-colors",
                session.id === activeSessionId
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-accent/50",
              )}
              onClick={() => onSelectSession(session.id)}
            >
              <MessageSquare className="w-4 h-4 shrink-0 text-muted-foreground" />
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">{session.title}</p>
                <p className="text-xs text-muted-foreground">
                  {formatTimestamp(session.createdAt)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="w-7 h-7 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSession(session.id);
                }}
              >
                <Trash2 className="w-3.5 h-3.5 text-muted-foreground" />
              </Button>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-sidebar-border">
        <p className="text-xs text-muted-foreground text-center">
          Healthcare Operations Assistant
        </p>
      </div>
    </aside>
  );
}
