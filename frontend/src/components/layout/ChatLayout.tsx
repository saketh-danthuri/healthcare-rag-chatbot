"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { ChatArea } from "@/components/chat/ChatArea";
import { CitationsPanel } from "@/components/citations/CitationsPanel";
import { useChat } from "@/hooks/useChat";
import { useHealth } from "@/hooks/useHealth";
import { useSessions } from "@/hooks/useSessions";
import type { Citation, ChatMessage } from "@/lib/types";

export function ChatLayout() {
  const {
    sessions,
    activeId,
    activeSession,
    createSession,
    switchSession,
    deleteSession,
    persistMessages,
  } = useSessions();

  const sessionId = activeId || "default";
  const { messages, isLoading, error, sendMessage, approveAction, setMessages } =
    useChat(sessionId);

  const { health } = useHealth();

  // Sidebar visibility (mobile)
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Citations panel
  const [citationsOpen, setCitationsOpen] = useState(false);
  const [activeCitations, setActiveCitations] = useState<Citation[]>([]);
  const [selectedCitationIndex, setSelectedCitationIndex] = useState<
    number | undefined
  >();

  // Persist messages to localStorage (does NOT trigger React state loop)
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const lastPersistedRef = useRef<ChatMessage[] | null>(null);

  useEffect(() => {
    // Skip if this is the same array reference we just loaded (prevents persist-after-load loop)
    if (messages === lastPersistedRef.current) return;
    if (messages.length > 0) {
      persistMessages(sessionIdRef.current, messages);
    }
  }, [messages, persistMessages]);

  // Load messages when switching sessions — depends on activeId (string), NOT activeSession (object)
  const prevSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (activeId && activeId !== prevSessionIdRef.current) {
      prevSessionIdRef.current = activeId;
      // Load messages from localStorage for the new session
      const stored = JSON.parse(
        localStorage.getItem("healthcare-chatbot-sessions") || "[]",
      ) as Array<{ id: string; messages: Array<{ timestamp: string } & Record<string, unknown>> }>;
      const sessionData = stored.find((s) => s.id === activeId);
      if (sessionData && sessionData.messages.length > 0) {
        const loaded = sessionData.messages.map((m) => ({
          ...m,
          timestamp: new Date(m.timestamp),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        })) as any;
        lastPersistedRef.current = loaded; // mark so persist effect skips this
        setMessages(loaded);
      } else {
        setMessages([]);
      }
      setCitationsOpen(false);
      setActiveCitations([]);
    }
  }, [activeId, setMessages]);

  const handleCitationClick = useCallback((citations: Citation[]) => {
    setActiveCitations(citations);
    setCitationsOpen(true);
    setSelectedCitationIndex(undefined);
  }, []);

  const handleNewChat = useCallback(() => {
    createSession();
    setSidebarOpen(false);
  }, [createSession]);

  // Responsive: detect desktop
  const [isDesktop, setIsDesktop] = useState(true);
  useEffect(() => {
    const check = () => setIsDesktop(window.innerWidth >= 1024);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar - always visible on desktop, overlay on mobile */}
      {(isDesktop || sidebarOpen) && (
        <>
          {!isDesktop && (
            <div
              className="fixed inset-0 bg-black/50 z-40"
              onClick={() => setSidebarOpen(false)}
            />
          )}
          <div
            className={
              !isDesktop ? "fixed left-0 top-0 h-full z-50" : "shrink-0"
            }
          >
            <Sidebar
              sessions={sessions}
              activeSessionId={activeSession?.id || null}
              onNewChat={handleNewChat}
              onSelectSession={(id) => {
                switchSession(id);
                setSidebarOpen(false);
              }}
              onDeleteSession={deleteSession}
              onClose={() => setSidebarOpen(false)}
              showCloseButton={!isDesktop}
            />
          </div>
        </>
      )}

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        <Header
          health={health}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          showMenuButton={!isDesktop}
        />
        <ChatArea
          messages={messages}
          isLoading={isLoading}
          error={error}
          onSendMessage={sendMessage}
          onCitationClick={handleCitationClick}
          onApproveAction={approveAction}
        />
      </main>

      {/* Citations panel */}
      {isDesktop && (
        <CitationsPanel
          citations={activeCitations}
          isOpen={citationsOpen}
          onClose={() => setCitationsOpen(false)}
          selectedIndex={selectedCitationIndex}
          onSelectCitation={setSelectedCitationIndex}
        />
      )}
    </div>
  );
}
