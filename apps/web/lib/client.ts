import type {
  ChatMessage,
  ChatResponse,
  AgentSpec,
  ProposedAction,
} from "@trg/shared";



const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type Difficulty = "trivial" | "medium" | "hard" | "expert";

interface ChatRequestPayload {
  project_id: string;
  message: string;
  audio_base64?: string;
  reply_with_audio?: boolean;
  agent_id?: string;
  conversation_history?: ChatMessage[];
}

export async function sendChat(req: ChatRequestPayload): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  return res.json();
}

export async function transcribe(audioBase64: string, language = "en") {
  const res = await fetch(`${BASE}/stt/transcribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audio_base64: audioBase64, language }),
  });
  if (!res.ok) throw new Error(`stt failed: ${res.status}`);
  return res.json();
}

export async function listAgents(): Promise<AgentSpec[]> {
  const res = await fetch(`${BASE}/agents`);
  if (!res.ok) throw new Error(`agents failed: ${res.status}`);
  return res.json();
}

export async function builderChat(
  user_message: string,
  history: { role: string; content: string }[] = [],
) {
  const res = await fetch(`${BASE}/builder/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_message, history }),
  });
  if (!res.ok) throw new Error(`builder failed: ${res.status}`);
  return res.json();
}

export async function createAgentFromSpec(spec: Record<string, unknown>) {
  const res = await fetch(`${BASE}/builder/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec }),
  });
  if (!res.ok) throw new Error(`create failed: ${res.status}`);
  return res.json();
}

export async function getAudit(project_id?: string, days = 30) {
  const qs = new URLSearchParams();
  if (project_id) qs.set("project_id", project_id);
  qs.set("days", String(days));
  const res = await fetch(`${BASE}/audit?${qs.toString()}`);
  if (!res.ok) throw new Error(`audit failed: ${res.status}`);
  return res.json();
}

export async function deleteProjectData(project_id: string) {
  const res = await fetch(`${BASE}/audit/project/${project_id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`delete failed: ${res.status}`);
  return res.json();
}

export async function executeAction(action: ProposedAction): Promise<{
  ok: boolean;
  action_id: string;
  action_type: string;
  artefact_path: string | null;
  error: string | null;
}> {
  const res = await fetch(`${BASE}/actions/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action_id: action.id,
      project_id: action.project_id,
      agent_id: action.agent_id,
      action_type: action.action_type,
      summary: action.summary,
      payload: action.payload,
      confidence: action.confidence,
      cited_chunk_ids: action.cited_chunk_ids,
    }),
  });
  if (!res.ok) throw new Error(`execute failed: ${res.status}`);
  return res.json();
}
