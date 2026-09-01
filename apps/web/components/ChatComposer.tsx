"use client";

import { Send, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { VoiceInput } from "./VoiceInput";

interface ChatComposerProps {
  onSend: (text: string, replyWithAudio: boolean) => void;
  busy: boolean;
  ttsEnabled: boolean;
  onTtsToggle: (next: boolean) => void;
}

export function ChatComposer({ onSend, busy, ttsEnabled, onTtsToggle }: ChatComposerProps) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize the textarea up to a cap
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [text]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    onSend(trimmed, ttsEnabled);
    setText("");
  };

  return (
    <div className="border-t border-white/10 bg-surface safe-area-bottom">
      <div className="flex items-end gap-2 p-3">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="Type or tap the mic…"
          className="flex-1 resize-none rounded-2xl bg-surface2 px-4 py-3 text-sm text-white placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/40 max-h-40"
        />
        <VoiceInput
          onTranscript={(t) => setText((prev) => (prev ? prev + " " + t : t))}
        />
        <button
          type="button"
          onClick={submit}
          disabled={busy || !text.trim()}
          aria-label="Send message"
          className="tap-large rounded-full bg-accent hover:bg-accentHover text-white p-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
        </button>
      </div>
      <div className="px-4 pb-2 flex items-center justify-between">
        <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={ttsEnabled}
            onChange={(e) => onTtsToggle(e.target.checked)}
            className="rounded border-white/20 bg-surface2 text-accent focus:ring-accent"
          />
          Read replies aloud
        </label>
        <span className="text-[10px] text-muted">Powered by Claude</span>
      </div>
    </div>
  );
}
