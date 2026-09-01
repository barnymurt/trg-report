// ─── Domain primitives ────────────────────────────────────────────────
//
// Note: field names match the Python backend (snake_case) so the JSON
// shapes line up exactly with what FastAPI returns.

export type ProjectId = string;
export type AgentId = string;
export type CollectionName = string;
export type ChunkId = string;

export type AgentTier =
  | "smollm2"      // local routing / compression / trivial Q&A
  | "haiku"        // routine summarisation, simple Q&A
  | "sonnet"       // complex reasoning, multi-doc synthesis
  | "sonnet-thinking"; // hardest problems with extended thinking

// ─── Agent ─────────────────────────────────────────────────────────────

export interface AgentSpec {
  id: AgentId;
  name: string;
  description: string;
  system_prompt: string;
  qdrant_collection: CollectionName;
  tools: string[];
  model_tiers: {
    trivial: AgentTier;
    medium: AgentTier;
    hard: AgentTier;
    expert: AgentTier;
  };
  starter_whitelist: WhitelistItem[];
  starter_blacklist: WhitelistItem[];
  parent_agent_id?: AgentId;
  created_at: string;
  created_by: "human" | "agent-builder";
}

export interface WhitelistItem {
  pattern: string;
  action_type: ActionType;
  enabled: boolean;
}

// ─── Messages ──────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  project_id: ProjectId;
  agent_id: AgentId;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  audio_url?: string;
  cited_chunks?: ChunkId[];
  faithfulness_score?: number;
  token_usage?: { input: number; output: number };
  tier?: AgentTier;
  proposed_actions?: ProposedAction[];
}

// ─── Proposed actions (human-in-the-loop) ─────────────────────────────

export type ActionType =
  | "create_calendar_event"
  | "draft_email"
  | "share_document"
  | "file_to_project"
  | "weekly_digest"
  | "contradiction_flag"
  | "extract_measurements"
  | "appointment_brief"
  | "create_agent"
  | "delete_data"
  | "modify_record"
  | "custom";

export interface ProposedAction {
  id: string;
  agent_id: AgentId;
  project_id: ProjectId;
  action_type: ActionType;
  summary: string;
  payload: Record<string, unknown>;
  confidence: number;
  cited_chunk_ids: ChunkId[];
  created_at: string;
  status: "pending" | "approved" | "rejected" | "edited" | "executed";
  whitelisted: boolean;
}

// ─── Retrieval ─────────────────────────────────────────────────────────

export interface RetrievalRequest {
  query: string;
  project_id: ProjectId;
  top_k?: number;
  final_k?: number;
  rerank?: boolean;
}

export interface RetrievedChunk {
  id: ChunkId;
  text: string;
  score: number;
  source: string;
  page?: number | null;
  project_id: ProjectId;
  metadata?: Record<string, unknown>;
}

// ─── Audit ─────────────────────────────────────────────────────────────

export interface AuditEntry {
  id: string;
  timestamp: string;
  project_id: ProjectId;
  agent_id: AgentId;
  tier: AgentTier;
  prompt_hash: string;
  retrieved_chunk_ids: ChunkId[];
  response_text: string;
  faithfulness_score?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_usd?: number;
}

// ─── Voice ─────────────────────────────────────────────────────────────

export interface TranscriptionRequest {
  audio: Blob;
  language?: string;
}

export interface TranscriptionResult {
  text: string;
  language: string;
  duration_sec: number;
}

export interface SynthesisRequest {
  text: string;
  voice?: string;
  speed?: number;
}

// ─── API surface ───────────────────────────────────────────────────────

export interface ChatRequest {
  project_id: ProjectId;
  message: string;
  audio_base64?: string;
  reply_with_audio?: boolean;
  agent_id?: string;
  conversation_history?: ChatMessage[];
}

export interface ChatResponse {
  response_text: string;
  cited_chunks: RetrievedChunk[];
  faithfulness_score: number;
  proposed_actions: ProposedAction[];
  tier_used: string;
  cost_usd: number;
  agent_id: string;
  audio_base64?: string | null;
}
