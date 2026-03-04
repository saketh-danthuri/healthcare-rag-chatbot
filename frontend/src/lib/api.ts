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
} from "./types";

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

export const api = {
  /** Send a chat message and get the agent's response */
  chat: (message: string, sessionId: string): Promise<ChatResponse> =>
    fetchJSON<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    }),

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
