"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, MessageSquare, Pencil, Trash2, X } from "lucide-react";
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
  onRenameSession: (id: string, title: string) => void;
  onClose?: () => void;
  showCloseButton?: boolean;
}

export function Sidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  onClose,
  showCloseButton,
}: SidebarProps) {
  // Search/filter over conversation titles.
  const [query, setQuery] = useState("");
  // Inline rename state.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const editInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const startRename = (session: ChatSession) => {
    setEditingId(session.id);
    setDraft(session.title);
  };

  const commitRename = () => {
    if (editingId) {
      const trimmed = draft.trim();
      if (trimmed) onRenameSession(editingId, trimmed);
    }
    setEditingId(null);
  };

  const cancelRename = () => setEditingId(null);

  const filtered = query.trim()
    ? sessions.filter((s) =>
        s.title.toLowerCase().includes(query.trim().toLowerCase()),
      )
    : sessions;

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

      {/* Search */}
      {sessions.length > 0 && (
        <div className="px-3 pt-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search conversations..."
            aria-label="Search conversations"
            className="w-full bg-muted rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground"
          />
        </div>
      )}

      {/* Session List */}
      <div className="flex-1 overflow-y-auto py-2">
        {sessions.length === 0 ? (
          <p className="text-xs text-muted-foreground px-3 py-4">
            No conversations yet. Start a new chat!
          </p>
        ) : filtered.length === 0 ? (
          <p className="text-xs text-muted-foreground px-3 py-4">
            No conversations match &ldquo;{query}&rdquo;.
          </p>
        ) : (
          filtered.map((session) => (
            <div
              key={session.id}
              className={cn(
                "group flex items-center gap-2 px-3 py-2.5 mx-2 rounded-lg cursor-pointer transition-colors",
                session.id === activeSessionId
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-accent/50",
              )}
              onClick={() => editingId !== session.id && onSelectSession(session.id)}
            >
              <MessageSquare className="w-4 h-4 shrink-0 text-muted-foreground" />
              <div className="flex-1 min-w-0">
                {editingId === session.id ? (
                  <input
                    ref={editInputRef}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onBlur={commitRename}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        commitRename();
                      } else if (e.key === "Escape") {
                        e.preventDefault();
                        cancelRename();
                      }
                    }}
                    aria-label="Conversation title"
                    className="w-full bg-background border border-input rounded px-1.5 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                ) : (
                  <>
                    <p className="text-sm truncate">{session.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatTimestamp(session.createdAt)}
                    </p>
                  </>
                )}
              </div>
              {editingId !== session.id && (
                <div className="flex items-center opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="w-7 h-7"
                    aria-label="Rename conversation"
                    title="Rename"
                    onClick={(e) => {
                      e.stopPropagation();
                      startRename(session);
                    }}
                  >
                    <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="w-7 h-7"
                    aria-label="Delete conversation"
                    title="Delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteSession(session.id);
                    }}
                  >
                    <Trash2 className="w-3.5 h-3.5 text-muted-foreground" />
                  </Button>
                </div>
              )}
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
