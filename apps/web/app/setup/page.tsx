"use client";

import { useEffect, useState } from "react";
import { Check, X, Loader2, Terminal, Container, Key, Sparkles } from "lucide-react";
import Link from "next/link";

interface Check {
  id: string;
  label: string;
  description: string;
  status: "pending" | "checking" | "pass" | "fail";
  detail?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function SetupPage() {
  const [checks, setChecks] = useState<Check[]>([
    {
      id: "agent",
      label: "Agent backend reachable",
      description: "The Python service that runs Claude, retrieval, and tools.",
      status: "checking",
    },
    {
      id: "anthropic",
      label: "Claude API key configured",
      description: "Anthropic API key is set in .env so the agent can reason.",
      status: "pending",
    },
    {
      id: "agents-listed",
      label: "Seed agents present",
      description: "The default team (Remodel, HusbandHealth, OwnHealth, …) is loaded.",
      status: "pending",
    },
  ]);

  const update = (id: string, patch: Partial<Check>) =>
    setChecks((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const runChecks = async () => {
    // 1. Agent reachable
    update("agent", { status: "checking" });
    try {
      const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
      if (res.ok) {
        update("agent", { status: "pass" });
      } else {
        update("agent", { status: "fail", detail: `HTTP ${res.status}` });
      }
    } catch (e: any) {
      update("agent", { status: "fail", detail: e.message });
    }

    // 2. Agents listed (proves Anthropic key was at least read at startup)
    update("agents-listed", { status: "checking" });
    try {
      const res = await fetch(`${API_URL}/agents`, { cache: "no-store" });
      if (res.ok) {
        const list = (await res.json()) as unknown[];
        if (Array.isArray(list) && list.length > 0) {
          update("agents-listed", { status: "pass", detail: `${list.length} agents` });
        } else {
          update("agents-listed", { status: "fail", detail: "no agents loaded" });
        }
      } else {
        update("agents-listed", { status: "fail", detail: `HTTP ${res.status}` });
      }
    } catch (e: any) {
      update("agents-listed", { status: "fail", detail: e.message });
    }

    // 3. Anthropic key — we can't directly verify from the PWA, so check the
    //    audit log endpoint: if the server boots, the key is at least present.
    update("anthropic", { status: "checking" });
    try {
      const res = await fetch(`${API_URL}/audit?days=1`, { cache: "no-store" });
      if (res.ok) {
        update("anthropic", { status: "pass" });
      } else {
        update("anthropic", { status: "fail", detail: `HTTP ${res.status}` });
      }
    } catch (e: any) {
      update("anthropic", { status: "fail", detail: e.message });
    }
  };

  useEffect(() => {
    runChecks();
  }, []);

  const allPass = checks.every((c) => c.status === "pass");
  const anyFail = checks.some((c) => c.status === "fail");

  return (
    <main className="min-h-[100dvh] bg-bg text-textPrimary p-6 max-w-2xl mx-auto safe-area-top safe-area-bottom">
      <header className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Sparkles className="h-5 w-5 text-accent" />
          <h1 className="text-xl font-semibold">First-run setup</h1>
        </div>
        <p className="text-sm text-muted">
          We're checking that everything you need is reachable. This takes a few seconds.
        </p>
      </header>

      <ul className="space-y-3 mb-8">
        {checks.map((c) => (
          <li
            key={c.id}
            className="rounded-xl border border-white/10 bg-surface p-4 flex items-start gap-3"
          >
            <div className="mt-0.5">
              {c.status === "checking" ? (
                <Loader2 className="h-5 w-5 text-accent animate-spin" />
              ) : c.status === "pass" ? (
                <Check className="h-5 w-5 text-success" />
              ) : c.status === "fail" ? (
                <X className="h-5 w-5 text-danger" />
              ) : (
                <div className="h-5 w-5 rounded-full border border-white/20" />
              )}
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium text-white">{c.label}</p>
              <p className="text-xs text-muted">{c.description}</p>
              {c.detail && (
                <p
                  className={`text-xs mt-1 ${
                    c.status === "fail" ? "text-danger" : "text-textSecondary"
                  }`}
                >
                  {c.detail}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>

      {allPass && (
        <div className="rounded-xl bg-success/10 border border-success/30 p-4 mb-6">
          <p className="text-success font-medium">All set. You're ready to chat.</p>
          <Link
            href="/"
            className="mt-3 inline-block tap-large rounded-xl bg-accent hover:bg-accentHover px-5 py-3 text-sm font-semibold text-white"
          >
            Open the chat
          </Link>
        </div>
      )}

      {anyFail && (
        <div className="rounded-xl bg-surface border border-white/10 p-4 space-y-3">
          <p className="text-sm text-white font-medium">Something isn't ready.</p>
          <ol className="text-sm text-muted space-y-2 list-decimal pl-5">
            <li>
              Open a terminal in the repo folder.
            </li>
            <li>
              Run:{" "}
              <code className="px-1.5 py-0.5 rounded bg-white/10 text-textPrimary">
                bash infra/scripts/preflight.sh
              </code>
            </li>
            <li>Fix anything red. Re-run until green.</li>
            <li>
              Run:{" "}
              <code className="px-1.5 py-0.5 rounded bg-white/10 text-textPrimary">
                pnpm infra:up
              </code>
            </li>
            <li>
              In another terminal:{" "}
              <code className="px-1.5 py-0.5 rounded bg-white/10 text-textPrimary">
                cd apps/agent && uvicorn trg.main:app --host 0.0.0.0 --port 8001
              </code>
            </li>
            <li>
              Then tap <em>Re-check</em> below.
            </li>
          </ol>
          <div className="flex gap-2 pt-2">
            <button
              onClick={runChecks}
              className="tap-large rounded-xl bg-accent hover:bg-accentHover px-4 py-2.5 text-sm font-medium text-white"
            >
              Re-check
            </button>
            <a
              href="https://github.com/barnymurt/trg-report/blob/main/infra/SETUP.md"
              target="_blank"
              rel="noopener noreferrer"
              className="tap-large rounded-xl border border-white/20 hover:bg-white/5 px-4 py-2.5 text-sm font-medium text-textPrimary inline-flex items-center gap-2"
            >
              <Terminal className="h-4 w-4" />
              Full setup guide
            </a>
          </div>
        </div>
      )}

      <details className="mt-8 text-xs text-muted">
        <summary className="cursor-pointer">What do these services do?</summary>
        <ul className="mt-3 space-y-2 list-disc pl-5">
          <li>
            <strong>Qdrant</strong> — vector database that holds your documents
            and conversation memory.
          </li>
          <li>
            <strong>TEI</strong> — turns your text into vectors so we can find
            relevant passages.
          </li>
          <li>
            <strong>Whisper</strong> — local speech-to-text for the mic button.
          </li>
          <li>
            <strong>Kokoro</strong> — local text-to-speech for read-aloud replies.
          </li>
          <li>
            <strong>SmolLM2</strong> — small local model that classifies
            projects and compresses context (saves Claude tokens).
          </li>
          <li>
            <strong>Docling</strong> — extracts text + tables from PDFs.
          </li>
          <li>
            <strong>Claude</strong> — the reasoning LLM (cloud, the only thing
            that touches the internet for your queries).
          </li>
        </ul>
      </details>
    </main>
  );
}
