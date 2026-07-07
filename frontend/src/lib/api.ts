/* ============================================================
   API Service Layer - All backend communication goes through here.

   DEV:  Uses Next.js rewrites proxy (/api/* -> localhost:8000/api/*)
   PROD: Uses NEXT_PUBLIC_API_URL to call the Azure Container App directly
   ============================================================ */

import type {
  ChatResponse,
  ActionApprovalRequest,
  ActionApprovalResponse,
  HealthStatus,
  StatsResponse,
  IngestResponse,
  FileUploadResponse,
  StreamEvent,
  StreamDeltaEvent,
  StreamFinalEvent,
  UserRole,
} from "./types";
import { getUserId } from "./role";

// In dev: empty string (relative URLs through Next.js rewrite proxy)
// In prod: full URL of the Azure Container App backend
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    let errorMessage: string;
    try {
      const body = await res.json();
      errorMessage = body.detail || JSON.stringify(body);
    } catch {
      errorMessage = `HTTP ${res.status}: ${res.statusText}`;
    }
    throw new ApiError(res.status, errorMessage);
  }

  return res.json();
}

export interface StreamHandlers {
  onStart?: (role: string) => void;
  onDelta?: (event: StreamDeltaEvent) => void;
  onFinal?: (event: StreamFinalEvent) => void;
  onError?: (detail: string) => void;
}

export const api = {
  /** Send a chat message and get the agent's response (non-streaming; fallback) */
  chat: (message: string, sessionId: string, fileId?: string): Promise<ChatResponse> =>
    fetchJSON<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId, file_id: fileId }),
    }),

  /**
   * Stream a chat response as NDJSON, PHI-masked server-side per role.
   * Reads the fetch body incrementally, parses one JSON object per line, and
   * dispatches typed events. The role is enforced by the server via X-User-Role.
   */
  chatStream: async (
    message: string,
    sessionId: string,
    fileId: string | undefined,
    role: UserRole,
    handlers: StreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    const res = await fetch(`${API_BASE}/api/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Role": role,
        "X-User-Id": getUserId(),
      },
      body: JSON.stringify({ message, session_id: sessionId, file_id: fileId }),
      signal,
    });

    if (!res.ok || !res.body) {
      let errorMessage: string;
      try {
        const body = await res.json();
        errorMessage = body.detail || JSON.stringify(body);
      } catch {
        errorMessage = `HTTP ${res.status}: ${res.statusText}`;
      }
      throw new ApiError(res.status, errorMessage);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const dispatch = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      let event: StreamEvent;
      try {
        event = JSON.parse(trimmed) as StreamEvent;
      } catch {
        return; // ignore malformed line
      }
      switch (event.type) {
        case "start":
          handlers.onStart?.(event.role);
          break;
        case "delta":
          handlers.onDelta?.(event);
          break;
        case "final":
          handlers.onFinal?.(event);
          break;
        case "error":
          handlers.onError?.(event.detail);
          break;
      }
    };

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex: number;
      while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        dispatch(line);
      }
    }
    // Flush any trailing (unterminated) line.
    if (buffer.trim()) dispatch(buffer);
  },

  /** Upload a meeting transcript file (.txt) */
  uploadFile: async (file: File): Promise<FileUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/api/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      let errorMessage: string;
      try {
        const body = await res.json();
        errorMessage = body.detail || JSON.stringify(body);
      } catch {
        errorMessage = `HTTP ${res.status}: ${res.statusText}`;
      }
      throw new ApiError(res.status, errorMessage);
    }

    return res.json();
  },

  /** Approve or reject a pending action */
  approveAction: (req: ActionApprovalRequest): Promise<ActionApprovalResponse> =>
    fetchJSON<ActionApprovalResponse>("/api/chat/approve", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  /** Get system health status */
  getHealth: (): Promise<HealthStatus> =>
    fetchJSON<HealthStatus>("/api/health"),

  /** Get retrieval system stats */
  getStats: (): Promise<StatsResponse> =>
    fetchJSON<StatsResponse>("/api/stats"),

  /** Trigger document ingestion */
  ingestDocuments: (): Promise<IngestResponse> =>
    fetchJSON<IngestResponse>("/api/ingest", { method: "POST" }),
};
