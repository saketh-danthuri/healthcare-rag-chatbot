"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Keeps a scroll container pinned to the bottom as new content arrives — but
 * only while the user is already near the bottom. If they scroll up to read
 * earlier messages, incoming tokens no longer yank them back down.
 *
 * Returns the container ref plus helpers to power a "jump to latest" button.
 */
export function useAutoScroll(dependency: unknown) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  // Mirror of isAtBottom read synchronously inside the auto-scroll effect
  // without adding it as a dependency (which would re-run on every scroll).
  const atBottomRef = useRef(true);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Within 80px of the bottom counts as "at bottom".
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    atBottomRef.current = atBottom;
    setIsAtBottom(atBottom);
  }, []);

  useEffect(() => {
    if (atBottomRef.current) scrollToBottom();
  }, [dependency, scrollToBottom]);

  return { scrollRef, isAtBottom, scrollToBottom, handleScroll };
}
