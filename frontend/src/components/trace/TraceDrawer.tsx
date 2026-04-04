import { motion, AnimatePresence } from "framer-motion";
import { X, Database, Wrench, AlertTriangle, Brain } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Trace } from "@/types";

interface Props {
  trace: Trace | null;
  open: boolean;
  onClose: () => void;
}

const SOURCE_TYPE_COLORS: Record<string, string> = {
  about:    "text-violet-400 bg-violet-950 border-violet-800",
  interest: "text-blue-400 bg-blue-950 border-blue-800",
  behavior: "text-emerald-400 bg-emerald-950 border-emerald-800",
  general:  "text-zinc-400 bg-zinc-900 border-zinc-700",
};

export function TraceDrawer({ trace, open, onClose }: Props) {
  return (
    <AnimatePresence>
      {open && trace && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 bottom-0 w-[360px] max-w-full z-50 bg-[--color-surface] border-l border-[--color-border] flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[--color-border]">
              <span className="text-[13px] font-semibold text-[--color-text]">Trace</span>
              <button
                onClick={onClose}
                className="p-1.5 rounded-[--radius-sm] text-[--color-text-3] hover:text-[--color-text] hover:bg-[--color-surface-2] transition-colors"
              >
                <X size={14} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-5">
              {/* Context utilization */}
              <section>
                <p className="text-[11px] text-[--color-text-3] uppercase tracking-wider font-medium mb-2">
                  Context
                </p>
                <div className="flex items-center justify-between text-[12px] text-[--color-text-2] mb-1.5">
                  <span>{trace.context_tokens.toLocaleString()} tokens</span>
                  <span className={cn(
                    "font-medium",
                    trace.context_pct >= 90 ? "text-[--color-danger]" :
                    trace.context_pct >= 70 ? "text-[--color-warning]" :
                    "text-[--color-success]"
                  )}>
                    {trace.context_pct}%
                  </span>
                </div>
                <div className="h-1.5 bg-[--color-surface-2] rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-500",
                      trace.context_pct >= 90 ? "bg-[--color-danger]" :
                      trace.context_pct >= 70 ? "bg-[--color-warning]" :
                      "bg-[--color-success]"
                    )}
                    style={{ width: `${Math.min(trace.context_pct, 100)}%` }}
                  />
                </div>
                <div className="flex items-center gap-4 mt-2 text-[11px] text-[--color-text-3]">
                  <span>{trace.first_token_ms}ms first token</span>
                  <span>{trace.total_ms}ms total</span>
                  <span>{trace.response_tokens} resp tokens</span>
                </div>
              </section>

              {/* RAG */}
              {trace.rag && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Database size={12} className="text-[--color-text-3]" />
                    <p className="text-[11px] text-[--color-text-3] uppercase tracking-wider font-medium">
                      RAG — {trace.rag.count} chunks · {trace.rag.duration_ms}ms
                    </p>
                  </div>
                  {trace.rag.chunks.length === 0 ? (
                    <p className="text-[12px] text-[--color-text-3] italic">No chunks matched threshold</p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {trace.rag.chunks.map((chunk, i) => (
                        <div key={i} className="bg-[--color-surface-2] border border-[--color-border] rounded-[--radius-sm] p-2.5">
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className={cn(
                              "text-[10px] font-medium px-1.5 py-0.5 rounded border",
                              SOURCE_TYPE_COLORS[chunk.source_type] ?? SOURCE_TYPE_COLORS.general
                            )}>
                              {chunk.source_type}
                            </span>
                            <span className="text-[11px] text-[--color-text-3] truncate">{chunk.source}</span>
                            <span className="ml-auto text-[11px] text-[--color-text-3] shrink-0">
                              {chunk.score.toFixed(3)}
                            </span>
                          </div>
                          <p className="text-[12px] text-[--color-text-2] leading-relaxed line-clamp-3">
                            {chunk.preview}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {/* Tool calls */}
              {trace.tool_calls.length > 0 && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Wrench size={12} className="text-[--color-text-3]" />
                    <p className="text-[11px] text-[--color-text-3] uppercase tracking-wider font-medium">
                      Tools
                    </p>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {trace.tool_calls.map((tc, i) => (
                      <div key={i} className={cn(
                        "flex items-center justify-between px-3 py-2 rounded-[--radius-sm] border text-[12px]",
                        tc.error
                          ? "bg-red-950/30 border-red-900 text-red-400"
                          : "bg-[--color-surface-2] border-[--color-border] text-[--color-text-2]"
                      )}>
                        <span className="font-mono">{tc.name}</span>
                        <span className="text-[--color-text-3]">{tc.duration_ms}ms</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Memory writes */}
              {trace.memory_writes.length > 0 && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Brain size={12} className="text-[--color-text-3]" />
                    <p className="text-[11px] text-[--color-text-3] uppercase tracking-wider font-medium">
                      Memory
                    </p>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {trace.memory_writes.map((w, i) => (
                      <div key={i} className="text-[12px] text-[--color-text-2] bg-[--color-surface-2] border border-[--color-border] rounded-[--radius-sm] px-3 py-2">
                        {w}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Warnings */}
              {trace.warnings.length > 0 && (
                <section>
                  <div className="flex items-center gap-1.5 mb-2">
                    <AlertTriangle size={12} className="text-[--color-warning]" />
                    <p className="text-[11px] text-[--color-warning] uppercase tracking-wider font-medium">
                      Warnings
                    </p>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    {trace.warnings.map((w, i) => (
                      <div key={i} className="text-[12px] text-yellow-300 bg-yellow-950/30 border border-yellow-900/50 rounded-[--radius-sm] px-3 py-2">
                        {w}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
