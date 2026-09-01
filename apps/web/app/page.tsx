"use client";

import { useEffect, useRef, useState } from "react";
import { Plus, FileText, Settings, History, X } from "lucide-react";
import { MessageBubble, type ChatMessageView } from "@/components/MessageBubble";
import { PendingActionsTray } from "@/components/PendingActionsTray";
import { ChatComposer } from "@/components/ChatComposer";
import { ProjectTabs, DEFAULT_TABS } from "@/components/ProjectTabs";
import { sendChat, listAgents, builderChat, createAgentFromSpec, getAudit, deleteProjectData, executeAction } from "@/lib/client";
import type { AgentSpec, ChatResponse, ProposedAction } from "@trg/shared";
import { toast } from "sonner";

type PendingState = Record<string, ProposedAction>;

export default function HomePage() {
  const [activeTab, setActiveTab] = useState(DEFAULT_TABS[0].id);
  const [messages, setMessages] = useState<Record<string, ChatMessageView[]>>({});
  const [pending, setPending] = useState<PendingState>({});
  const [busy, setBusy] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [agents, setAgents] = useState<AgentSpec[]>([]);
  const [showBuilder, setShowBuilder] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load agents on mount
  useEffect(() => {
    listAgents()
      .then(setAgents)
      .catch((e) => toast.error(`Couldn't reach agent backend: ${e.message}`));
  }, []);

  // Auto-scroll on new message
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  const activeMessages = messages[activeTab] || [];
  const activePending = Object.values(pending).filter((a) => a.project_id === activeTab);

  const send = async (text: string, replyWithAudio: boolean) => {
    setBusy(true);
    const userMsg: ChatMessageView = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((m) => ({ ...m, [activeTab]: [...(m[activeTab] || []), userMsg] }));
    try {
      const res: ChatResponse = await sendChat({
        project_id: activeTab,
        message: text,
        reply_with_audio: replyWithAudio,
      });
      const assistant: ChatMessageView = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: res.response_text,
        audioBase64: res.audio_base64 ?? undefined,
        citedChunks: res.cited_chunks.map((c) => ({
          id: c.id,
          source: c.source,
          page: c.page,
        })),
        faithfulnessScore: res.faithfulness_score,
        tier: res.tier_used,
        proposedActionCount: res.proposed_actions.length,
        timestamp: new Date().toISOString(),
      };
      setMessages((m) => ({ ...m, [activeTab]: [...(m[activeTab] || []), assistant] }));
      // Add proposed actions
      const newPending: PendingState = {};
      res.proposed_actions.forEach((a) => {
        newPending[a.id] = a;
      });
      setPending((p) => ({ ...p, ...newPending }));
    } catch (e: any) {
      toast.error(`Send failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id: string) => {
    const a = pending[id];
    if (!a) return;
    try {
      const res = await executeAction(a);
      if (res.ok) {
        const where = res.artefact_path ? ` → ${res.artefact_path}` : "";
        toast.success(`Approved: ${a.summary}${where}`);
      } else {
        toast.error(`Approval failed: ${res.error ?? "unknown error"}`);
      }
    } catch (e: any) {
      toast.error(`Approval error: ${e.message}`);
    } finally {
      setPending((p) => {
        const next = { ...p };
        delete next[id];
        return next;
      });
    }
  };
  const reject = (id: string) => {
    setPending((p) => {
      const next = { ...p };
      delete next[id];
      return next;
    });
    toast("Rejected");
  };
  const edit = (id: string) => {
    toast("Edit flow coming soon — for now, approve or reject.");
  };

  return (
    <main className="flex h-[100dvh] flex-col bg-bg text-textPrimary">
      {/* ─── Top bar ──────────────────────────────────────────────── */}
      <header className="flex items-center justify-between safe-area-top px-4 py-3 border-b border-white/10 bg-surface">
        <div>
          <h1 className="text-base font-semibold">TRG</h1>
          <p className="text-xs text-muted">
            {agents.length} agent{agents.length === 1 ? "" : "s"} · voice-first
          </p>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setShowBuilder(true)}
            className="tap-large rounded-full p-2 text-muted hover:text-white hover:bg-white/5"
            aria-label="Create new agent"
            title="Create new agent"
          >
            <Plus className="h-5 w-5" />
          </button>
          <button
            onClick={() => setShowAudit(true)}
            className="tap-large rounded-full p-2 text-muted hover:text-white hover:bg-white/5"
            aria-label="View audit log"
            title="Audit log"
          >
            <History className="h-5 w-5" />
          </button>
        </div>
      </header>

      {/* ─── Project tabs ──────────────────────────────────────────── */}
      <ProjectTabs activeId={activeTab} onChange={setActiveTab} />

      {/* ─── Messages ─────────────────────────────────────────────── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 space-y-3">
        {activeMessages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-sm px-4">
              <div className="text-5xl mb-3">🎙️</div>
              <h2 className="text-lg font-medium text-white mb-1">
                Tap the mic and ask anything.
              </h2>
              <p className="text-sm text-muted">
                I'm here to keep your projects tracked, your documents organised,
                and your inbox calm — without being another thing to manage.
              </p>
            </div>
          </div>
        ) : (
          activeMessages.map((m) => <MessageBubble key={m.id} msg={m} />)
        )}
      </div>

      {/* ─── Pending actions + composer ───────────────────────────── */}
      {activePending.length > 0 && (
        <PendingActionsTray
          actions={activePending}
          onApprove={approve}
          onReject={reject}
          onEdit={edit}
        />
      )}
      <ChatComposer
        onSend={send}
        busy={busy}
        ttsEnabled={ttsEnabled}
        onTtsToggle={setTtsEnabled}
      />

      {/* ─── Modals ───────────────────────────────────────────────── */}
      {showBuilder && <BuilderModal onClose={() => setShowBuilder(false)} onCreated={() => listAgents().then(setAgents)} />}
      {showAudit && <AuditModal onClose={() => setShowAudit(false)} />}
    </main>
  );
}

// ─── AgentBuilder modal ────────────────────────────────────────────────

function BuilderModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [history, setHistory] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      setBusy(true);
      const opening = "Hello — what should this new agent do?";
      setHistory([{ role: "assistant", content: opening }]);
      setBusy(false);
    })();
  }, []);

  const send = async () => {
    if (!input.trim() || busy) return;
    const userMsg = input.trim();
    setInput("");
    setBusy(true);
    const nextHistory: typeof history = [
      ...history,
      { role: "user" as const, content: userMsg },
    ];
    setHistory(nextHistory);
    try {
      const res = await builderChat(userMsg, []); // server keeps its own history
      setHistory([
        ...nextHistory,
        { role: "assistant" as const, content: res.assistant_message },
      ]);
      if (res.draft_spec) setDraft(res.draft_spec);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!draft) return;
    setBusy(true);
    try {
      await createAgentFromSpec(draft);
      toast.success("New agent created!");
      onCreated();
      onClose();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur flex items-end sm:items-center justify-center">
      <div className="bg-bg w-full max-w-2xl max-h-[90vh] rounded-t-2xl sm:rounded-2xl border border-white/10 flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div>
            <h2 className="font-semibold">Create a new agent</h2>
            <p className="text-xs text-muted">Talk it through — I'll ask if I need more.</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="tap-large rounded p-2 text-muted">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-3">
          {history.map((m, i) => (
            <div
              key={i}
              className={`rounded-xl px-3 py-2 text-sm max-w-[90%] ${
                m.role === "user"
                  ? "ml-auto bg-accent text-white"
                  : "bg-surface text-textPrimary"
              }`}
            >
              {m.content}
            </div>
          ))}
          {draft && (
            <div className="rounded-xl border border-accent/30 bg-accent/10 p-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs uppercase tracking-wider text-accent">Draft ready</p>
                <button
                  onClick={create}
                  disabled={busy}
                  className="tap-large rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                >
                  Create agent
                </button>
              </div>
              <pre className="text-xs overflow-x-auto text-textSecondary">
                {JSON.stringify(draft, null, 2)}
              </pre>
            </div>
          )}
        </div>
        <div className="border-t border-white/10 p-3 flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Describe what you want…"
            className="flex-1 rounded-xl bg-surface2 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="tap-large rounded-xl bg-accent px-4 text-sm font-medium text-white disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Audit log modal ────────────────────────────────────────────────────

function AuditModal({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [tab, setTab] = useState<"claude" | "actions">("claude");
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    getAudit(undefined, 30)
      .then(setData)
      .catch(() => setData({ claude_calls: [], action_events: [], total_cost_usd: 0 }));
  }, []);

  const wipe = async (projectId: string) => {
    if (!confirm(`Permanently delete all data for project "${projectId}"?`)) return;
    setDeleting(projectId);
    try {
      await deleteProjectData(projectId);
      toast.success(`Deleted audit entries for ${projectId}`);
      const fresh = await getAudit(undefined, 30);
      setData(fresh);
    } finally {
      setDeleting(null);
    }
  };

  const claudeCalls: any[] = data?.claude_calls ?? [];
  const actionEvents: any[] = data?.action_events ?? [];

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur flex items-end sm:items-center justify-center">
      <div className="bg-bg w-full max-w-3xl max-h-[90vh] rounded-t-2xl sm:rounded-2xl border border-white/10 flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div>
            <h2 className="font-semibold">Audit log — last 30 days</h2>
            <p className="text-xs text-muted">
              {data?.total_cost_usd != null
                ? `Total spend: $${data.total_cost_usd.toFixed(4)}`
                : "…"}
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="tap-large rounded p-2 text-muted">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex gap-2 px-4 pt-2 border-b border-white/5">
          <button
            onClick={() => setTab("claude")}
            className={`px-3 py-1.5 text-xs rounded-t-lg ${tab === "claude" ? "bg-surface text-white" : "text-muted"}`}
          >
            Claude calls ({claudeCalls.length})
          </button>
          <button
            onClick={() => setTab("actions")}
            className={`px-3 py-1.5 text-xs rounded-t-lg ${tab === "actions" ? "bg-surface text-white" : "text-muted"}`}
          >
            Actions ({actionEvents.length})
          </button>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-2">
          {!data ? (
            <p className="text-sm text-muted">Loading…</p>
          ) : tab === "claude" ? (
            claudeCalls.length === 0 ? (
              <p className="text-sm text-muted">No Claude calls yet.</p>
            ) : (
              claudeCalls.map((e: any) => (
                <div key={e.id} className="rounded-lg bg-surface p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-textPrimary">{e.prompt_summary}</p>
                      <p className="text-xs text-muted">
                        {e.timestamp} · {e.project_id} · {e.tier} ·{" "}
                        {e.input_tokens}in/{e.output_tokens}out · ${e.cost_usd.toFixed(4)}
                      </p>
                    </div>
                    <button
                      onClick={() => wipe(e.project_id)}
                      disabled={deleting === e.project_id}
                      className="tap-large text-xs text-danger border border-danger/30 rounded-lg px-2 py-1"
                    >
                      Wipe project
                    </button>
                  </div>
                </div>
              ))
            )
          ) : actionEvents.length === 0 ? (
            <p className="text-sm text-muted">No actions executed yet.</p>
          ) : (
            actionEvents.map((e: any) => (
              <div key={e.id} className="rounded-lg bg-surface p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-textPrimary">
                      {e.kind} · {e.action_type}
                    </p>
                    <p className="text-xs text-muted">
                      {e.timestamp} · {e.project_id || "—"} ·{" "}
                      <span className={e.ok ? "text-success" : "text-danger"}>
                        {e.ok ? "ok" : "failed"}
                      </span>
                    </p>
                    {e.artefact_path && (
                      <p className="text-[10px] text-muted truncate">→ {e.artefact_path}</p>
                    )}
                    {e.error && <p className="text-[10px] text-danger">{e.error}</p>}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
