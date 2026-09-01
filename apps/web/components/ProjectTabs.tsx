"use client";

import { Home, Hammer, HeartPulse, Stethoscope, Calendar, Inbox } from "lucide-react";
import clsx from "clsx";

export interface ProjectTab {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  agentId?: string;
}

export const DEFAULT_TABS: ProjectTab[] = [
  { id: "remodel", label: "Remodel", icon: Hammer },
  { id: "husband-health", label: "Husband", icon: HeartPulse },
  { id: "own-health", label: "Self", icon: Stethoscope },
  { id: "calendar", label: "Calendar", icon: Calendar },
  { id: "inbox", label: "Inbox", icon: Inbox },
];

interface ProjectTabsProps {
  tabs?: ProjectTab[];
  activeId: string;
  onChange: (id: string) => void;
}

export function ProjectTabs({ tabs = DEFAULT_TABS, activeId, onChange }: ProjectTabsProps) {
  return (
    <nav
      className="flex gap-2 overflow-x-auto scrollbar-thin px-4 py-2 border-b border-white/10 bg-surface"
      aria-label="Project tabs"
    >
      {tabs.map((t) => {
        const Icon = t.icon;
        const active = t.id === activeId;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={clsx(
              "tap-large flex items-center gap-2 whitespace-nowrap rounded-full px-4 py-2 text-sm font-medium transition-all",
              active
                ? "bg-accent text-white"
                : "bg-white/5 text-textSecondary hover:bg-white/10",
            )}
            aria-pressed={active}
          >
            <Icon className="h-4 w-4" />
            {t.label}
          </button>
        );
      })}
    </nav>
  );
}
