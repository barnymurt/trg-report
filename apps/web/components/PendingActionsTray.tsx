"use client";

import { Check, X, Edit3, Clock } from "lucide-react";
import type { ProposedAction } from "@trg/shared";

interface PendingActionsTrayProps {
  actions: ProposedAction[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onEdit: (id: string) => void;
}

const ACTION_ICONS: Record<string, string> = {
  create_calendar_event: "📅",
  draft_email: "✉️",
  share_document: "📤",
  file_to_project: "📁",
  weekly_digest: "📊",
  contradiction_flag: "⚠️",
  extract_measurements: "📐",
  appointment_brief: "🩺",
  create_agent: "🤖",
  delete_data: "🗑️",
  modify_record: "✏️",
  custom: "⚙️",
};

export function PendingActionsTray({
  actions,
  onApprove,
  onReject,
  onEdit,
}: PendingActionsTrayProps) {
  if (!actions.length) return null;
  return (
    <div className="border-t border-white/10 bg-surface/95 backdrop-blur safe-area-bottom">
      <div className="px-4 py-2 flex items-center gap-2 text-xs text-muted">
        <Clock className="h-3 w-3" />
        <span>{actions.length} pending action{actions.length === 1 ? "" : "s"}</span>
      </div>
      <div className="space-y-2 px-4 pb-4 max-h-72 overflow-y-auto scrollbar-thin">
        {actions.map((a) => (
          <div
            key={a.id}
            className="rounded-xl border border-white/10 bg-surface2 p-3"
          >
            <div className="flex items-start gap-2">
              <div className="text-xl">{ACTION_ICONS[a.action_type] || "⚙️"}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-white truncate">
                    {a.summary}
                  </p>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-muted whitespace-nowrap">
                    {Math.round(a.confidence * 100)}%
                  </span>
                </div>
                <p className="text-[10px] text-muted mt-0.5">
                  {a.action_type.replace(/_/g, " ")}
                </p>
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              <button
                onClick={() => onApprove(a.id)}
                className="flex-1 tap-large flex items-center justify-center gap-1 rounded-lg bg-success text-white text-sm font-medium py-2"
                aria-label="Approve action"
              >
                <Check className="h-4 w-4" /> Approve
              </button>
              <button
                onClick={() => onEdit(a.id)}
                className="tap-large flex items-center justify-center rounded-lg border border-white/20 text-white px-3"
                aria-label="Edit action"
              >
                <Edit3 className="h-4 w-4" />
              </button>
              <button
                onClick={() => onReject(a.id)}
                className="tap-large flex items-center justify-center rounded-lg bg-white/5 text-muted hover:text-white px-3"
                aria-label="Reject action"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
