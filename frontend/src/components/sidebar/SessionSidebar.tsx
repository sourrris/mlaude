import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, RefreshCw, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface Props {
  sessions: Session[];
  activeSessionId: string | null;
  onNew: () => void;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onReindex: () => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function SessionSidebar({ sessions, activeSessionId, onNew, onLoad, onDelete, onReindex }: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <aside className="w-[240px] min-w-[240px] flex flex-col h-full border-r border-[--color-border] bg-[--color-surface]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[--color-border]">
        <span className="text-[13px] font-semibold tracking-tight text-[--color-text]">
          mlaude
        </span>
        <button
          onClick={onNew}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[--radius-sm] text-[12px] font-medium text-[--color-text-2] hover:text-[--color-text] hover:bg-[--color-surface-2] transition-colors"
          title="New chat"
        >
          <Plus size={13} />
          New
        </button>
      </div>

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto py-2 px-2">
        {sessions.length === 0 ? (
          <p className="text-[12px] text-[--color-text-3] px-2 py-3 text-center">
            No sessions yet
          </p>
        ) : (
          <AnimatePresence initial={false}>
            {sessions.map((s) => (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.15 }}
                onMouseEnter={() => setHoveredId(s.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  "group flex items-center gap-2 px-2.5 py-2 rounded-[--radius-sm] cursor-pointer mb-0.5",
                  "transition-colors duration-[--duration-fast]",
                  s.id === activeSessionId
                    ? "bg-[--color-surface-2] text-[--color-text]"
                    : "text-[--color-text-2] hover:bg-[--color-surface-2] hover:text-[--color-text]"
                )}
                onClick={() => onLoad(s.id)}
              >
                <MessageSquare size={12} className="shrink-0 opacity-40" />
                <span className="flex-1 text-[13px] truncate leading-snug">
                  {s.title ?? "New chat"}
                </span>
                <span className="text-[11px] text-[--color-text-3] shrink-0 hidden group-hover:hidden">
                  {hoveredId !== s.id && formatTime(s.updated_at)}
                </span>
                {hoveredId === s.id && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                    className="shrink-0 p-1 rounded hover:text-[--color-danger] text-[--color-text-3] transition-colors"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </nav>

      {/* Footer */}
      <div className="px-3 py-3 border-t border-[--color-border]">
        <button
          onClick={onReindex}
          className="flex items-center gap-2 w-full px-2.5 py-2 rounded-[--radius-sm] text-[12px] text-[--color-text-3] hover:text-[--color-text-2] hover:bg-[--color-surface-2] transition-colors"
          title="Re-index knowledge base"
        >
          <RefreshCw size={11} />
          Reindex knowledge
        </button>
      </div>
    </aside>
  );
}
