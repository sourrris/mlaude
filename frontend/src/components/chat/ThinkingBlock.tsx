import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight } from "lucide-react";

interface Props {
  thinking: string;
  isStreaming: boolean;
  durationSeconds?: number | null;
}

export function ThinkingBlock({ thinking, isStreaming, durationSeconds }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (isStreaming) {
    return (
      <div className="mb-3 w-full">
        <div className="flex items-center gap-2 mb-1.5">
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-[#d97757]"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.2, repeat: Infinity }}
          />
          <span className="text-[12px] font-medium text-zinc-400 tracking-wide">
            Thinking…
          </span>
        </div>
        {thinking && (
          <div className="pl-3.5 border-l-2 border-zinc-200 max-h-[160px] overflow-y-auto">
            <p className="text-[12px] text-zinc-400 leading-relaxed font-mono whitespace-pre-wrap">
              {thinking}
            </p>
          </div>
        )}
      </div>
    );
  }

  if (!thinking) return null;

  const label =
    durationSeconds != null && durationSeconds > 0
      ? `Thought for ${durationSeconds}s`
      : "Thought";

  return (
    <div className="mb-3 w-full">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1 text-[12px] text-zinc-400 hover:text-zinc-600 transition-colors group"
      >
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center"
        >
          <ChevronRight size={13} />
        </motion.span>
        <span>{label}</span>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="thinking-expanded"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-2 pl-3.5 border-l-2 border-zinc-200 max-h-[280px] overflow-y-auto">
              <p className="text-[12px] text-zinc-400 leading-relaxed font-mono whitespace-pre-wrap py-1">
                {thinking}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
