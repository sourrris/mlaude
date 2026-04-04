import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, RefreshCw, MessageSquare, BrainCircuit } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface Props {
  sessions: Session[];
  activeSessionId: string | null;
  onNew: () => void;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onReindex: () => void;
  onOpenMemory: () => void;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60_000) return "now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onNew,
  onLoad,
  onDelete,
  onReindex,
  onOpenMemory,
}: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <aside className="w-60 min-w-60 flex flex-col h-full bg-zinc-900 border-r border-zinc-800">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md bg-amber-400 flex items-center justify-center">
            <span className="text-black text-[10px] font-bold leading-none">m</span>
          </div>
          <span className="text-[13px] font-semibold text-zinc-100 tracking-tight">mlaude</span>
        </div>
        <button
          onClick={onNew}
          className="flex items-center gap-1 px-2 py-1.5 rounded-md text-[12px] font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors duration-100"
          title="New chat"
        >
          <Plus size={13} />
          New
        </button>
      </div>

      {/* Sessions */}
      <nav className="flex-1 overflow-y-auto py-2 px-1.5">
        {sessions.length === 0 ? (
          <p className="text-[12px] text-zinc-600 px-3 py-4 text-center">No sessions yet</p>
        ) : (
          <AnimatePresence initial={false}>
            {sessions.map((s) => (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.15 }}
                onMouseEnter={() => setHoveredId(s.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  "group flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer mb-0.5",
                  "transition-colors duration-100",
                  s.id === activeSessionId
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                )}
                onClick={() => onLoad(s.id)}
              >
                <MessageSquare
                  size={12}
                  className={cn(
                    "shrink-0",
                    s.id === activeSessionId ? "text-amber-400" : "text-zinc-600"
                  )}
                />
                <span className="flex-1 text-[13px] truncate leading-snug">
                  {s.title ?? "New chat"}
                </span>
                {hoveredId === s.id ? (
                  <button
                    onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                    className="shrink-0 p-0.5 rounded text-zinc-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={12} />
                  </button>
                ) : (
                  <span className="text-[10px] text-zinc-600 shrink-0">
                    {formatTime(s.updated_at)}
                  </span>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </nav>

      {/* Footer */}
      <div className="px-1.5 py-2 border-t border-zinc-800 flex flex-col gap-0.5">
        <button
          onClick={onOpenMemory}
          className="flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-[12px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
        >
          <BrainCircuit size={13} />
          Memory
        </button>
        <button
          onClick={onReindex}
          className="flex items-center gap-2 w-full px-2.5 py-2 rounded-lg text-[12px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
        >
          <RefreshCw size={13} />
          Reindex knowledge
        </button>
      </div>
    </aside>
  );
}
