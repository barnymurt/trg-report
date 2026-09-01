"use client";

import { Volume2, FileText, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { base64ToBlobUrl } from "@/lib/audio";
import clsx from "clsx";

export interface ChatMessageView {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  audioBase64?: string;
  citedChunks?: { id: string; source: string; page?: number | null }[];
  faithfulnessScore?: number;
  tier?: string;
  proposedActionCount?: number;
  timestamp: string;
}

export function MessageBubble({ msg }: { msg: ChatMessageView }) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const isUser = msg.role === "user";
  const isAssistant = msg.role === "assistant";

  const playAudio = () => {
    if (audioUrl) {
      audioUrl;
      const a = new Audio(audioUrl);
      a.play();
      return;
    }
    if (msg.audioBase64) {
      const url = base64ToBlobUrl(msg.audioBase64);
      setAudioUrl(url);
      const a = new Audio(url);
      a.play();
    }
  };

  // Render citation tokens like [chunk-3] as small superscripts
  const rendered = renderCitations(msg.content);

  return (
    <div
      className={clsx(
        "flex",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      <div
        className={clsx(
          "max-w-[88%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-accent text-white rounded-br-sm"
            : "bg-surface text-textPrimary rounded-bl-sm",
        )}
      >
        <div className="prose prose-invert prose-sm max-w-none">{rendered}</div>

        {isAssistant && msg.citedChunks && msg.citedChunks.length > 0 && (
          <div className="mt-3 pt-2 border-t border-white/10 space-y-1">
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted">
              <FileText className="h-3 w-3" />
              <span>Sources ({msg.citedChunks.length})</span>
              {typeof msg.faithfulnessScore === "number" && (
                <span className="ml-auto flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3 text-success" />
                  {Math.round(msg.faithfulnessScore * 100)}%
                </span>
              )}
              {msg.tier && (
                <span className="ml-2 px-1.5 py-0.5 rounded bg-white/10 text-muted">
                  {msg.tier}
                </span>
              )}
            </div>
            <div className="space-y-0.5">
              {msg.citedChunks.map((c, i) => (
                <p key={c.id} className="text-[10px] text-muted truncate">
                  [{i + 1}] {c.source}
                  {c.page ? ` · p.${c.page}` : ""}
                </p>
              ))}
            </div>
          </div>
        )}

        {isAssistant && msg.audioBase64 && (
          <button
            type="button"
            onClick={playAudio}
            className="mt-2 flex items-center gap-1 text-xs text-accent"
            aria-label="Play reply audio"
          >
            <Volume2 className="h-3 w-3" /> Listen
          </button>
        )}
      </div>
    </div>
  );
}

function renderCitations(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const regex = /\[chunk-(\d+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      out.push(text.slice(lastIndex, match.index));
    }
    out.push(
      <span key={`${match.index}-${match[1]}`} className="cite">
        [{match[1]}]
      </span>,
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) out.push(text.slice(lastIndex));
  return out;
}
