/* ============================================================
   TypeScript interfaces matching the FastAPI backend models.
   See: backend/app/api/routes.py, backend/app/agent/state.py
   ============================================================ */

// --- Citation (from retriever.py search_and_format) ---
export interface Citation {
  index: number;
  source_file: string;
  section: string;
  job_id: string;
  page_number: string | number;
  score: number;
  snippet: string;
}

// --- Pending Action (from graph.py - agent proposes action needing approval) ---
export interface PendingAction {
  tool_name: string;
  arguments: Record<string, unknown>;
  status: string;
}

// --- Action Result (from /api/chat/approve response) ---
export interface ActionResult {
  success: boolean;
  message: string;
  result?: Record<string, unknown>;
}

// --- Chat Message (frontend display model) ---
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  citations?: Citation[];
  pendingAction?: PendingAction;
  actionResult?: ActionResult;
}

// --- Chat Session (frontend session management) ---
export interface ChatSession {
  id: string;
  title: string;
  createdAt: Date;
  messages: ChatMessage[];
}

// --- Health Status (from /api/health) ---
export interface HealthStatus {
  status: "healthy" | "degraded" | "offline";
  version: string;
  search_connected: boolean;
  documents_indexed: number;
}

// --- API Request/Response types ---
export interface ChatRequest {
  message: string;
  session_id: string;
}

export interface ChatResponse {
  response: string;
  citations: Citation[];
  pending_action: PendingAction | null;
  session_id: string;
}

export interface ActionApprovalRequest {
  session_id: string;
  action_type: string;
  approved: boolean;
  parameters: Record<string, unknown>;
}

export interface ActionApprovalResponse {
  success: boolean;
  message: string;
  result?: Record<string, unknown>;
}

export interface IngestResponse {
  documents_loaded: number;
  chunks_created: number;
  chunks_indexed: number;
  docs_path: string;
}

export interface StatsResponse {
  index_name: string;
  total_chunks: number;
  search_endpoint: string;
}
