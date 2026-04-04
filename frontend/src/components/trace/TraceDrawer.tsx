import { motion, AnimatePresence } from "framer-motion";
import { X, Database, Wrench, AlertTriangle, Brain } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Trace } from "@/types";

interface Props {
  trace: Trace | null;
  open: boolean;
  onClose: () => void;
}

const SOURCE_BADGE: Record<string, string> = {
  about:    "text-violet-300 bg-violet-950/60 border-violet-800/60",
  interest: "text-blue-300 bg-blue-950/60 border-blue-800/60",
  behavior: "text-emerald-300 bg-emerald-950/60 border-emerald-800/60",
  general:  "text-zinc-400 bg-zinc-800 border-zinc-700",
};

function SectionLabel({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex items-center gap-1.5 mb-2.5">
      <Icon size={12} className="text-zinc-600" />
      <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest">{label}</span>
    </div>
  );
}

export function TraceDrawer({ trace, open, onClose }: Props) {
  return (
    <AnimatePresence>
      {open && trace && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 bg-black/50 z-40"
            onClick={onClose}
          />

          <motion.aside
            key="panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
            className="fixed right-0 top-0 bottom-0 w-[340px] z-50 bg-zinc-900 border-l border-zinc-800 flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-zinc-800">
              <span className="text-[13px] font-semibold text-zinc-100">Request trace</span>
              <button
                onClick={onClose}
                className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
              >
                <X size={14} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-6">

              {/* Context */}
              <section>
                <SectionLabel icon={Database} label="Context" />
                <div className="flex justify-between text-[12px] text-zinc-400 mb-2">
                  <span>{trace.context_tokens.toLocaleString()} tokens used</span>
                  <span className={cn(
                    "font-semibold",
                    trace.context_pct >= 90 ? "text-red-400" :
                    trace.context_pct >= 70 ? "text-amber-400" :
                    "text-emerald-400"
                  )}>
                    {trace.context_pct}%
                  </span>
                </div>
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(trace.context_pct, 100)}%` }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                    className={cn(
                      "h-full rounded-full",
                      trace.context_pct >= 90 ? "bg-red-500" :
                      trace.context_pct >= 70 ? "bg-amber-400" :
                      "bg-emerald-500"
                    )}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2 mt-3">
                  {[
                    { label: "First token", value: `${trace.first_token_ms}ms` },
                    { label: "Total", value: `${trace.total_ms}ms` },
                    { label: "Response", value: `${trace.response_tokens} tok` },
                  ].map((m) => (
                    <div key={m.label} className="bg-zinc-800/60 rounded-lg px-2.5 py-2 text-center">
                      <p className="text-[13px] font-semibold text-zinc-200">{m.value}</p>
                      <p className="text-[10px] text-zinc-600 mt-0.5">{m.label}</p>
                    </div>
                  ))}
                </div>
              </section>

              {/* RAG */}
              {trace.rag && (
                <section>
                  <SectionLabel icon={Database} label={`RAG · ${trace.rag.count} chunks · ${trace.rag.duration_ms}ms`} />
                  {trace.rag.chunks.length === 0 ? (
                    <p className="text-[12px] text-zinc-600 italic">No chunks matched</p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {trace.rag.chunks.map((chunk, i) => (
                        <div key={i} className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-3">
                          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                            <span className={cn(
                              "text-[10px] font-medium px-1.5 py-0.5 rounded-md border",
                              SOURCE_BADGE[chunk.source_type] ?? SOURCE_BADGE.general
                            )}>
                              {chunk.source_type}
                            </span>
                            <span className="text-[11px] text-zinc-500 truncate flex-1 min-w-0">
                              {chunk.source}
                            </span>
                            <span className="text-[11px] text-zinc-600 tabular-nums shrink-0">
                              {chunk.score.toFixed(3)}
                            </span>
                          </div>
                          <p className="text-[12px] text-zinc-400 leading-relaxed line-clamp-3">
                            {chunk.preview}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {/* Tools */}
              {trace.tool_calls.length > 0 && (
                <section>
                  <SectionLabel icon={Wrench} label="Tools" />
                  <div className="flex flex-col gap-1.5">
                    {trace.tool_calls.map((tc, i) => (
                      <div key={i} className={cn(
                        "flex items-center justify-between px-3 py-2.5 rounded-xl border text-[12px]",
                        tc.error
                          ? "bg-red-950/30 border-red-900/60 text-red-400"
                          : "bg-zinc-800/50 border-zinc-700/50 text-zinc-300"
                      )}>
                        <span className="font-mono">{tc.name}</span>
                        <span className="text-zinc-500 tabular-nums">{tc.duration_ms}ms</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Memory */}
              {trace.memory_writes.length > 0 && (
                <section>
                  <SectionLabel icon={Brain} label="Memory" />
                  <div className="flex flex-col gap-1.5">
                    {trace.memory_writes.map((w, i) => (
                      <div key={i} className="text-[12px] text-zinc-400 bg-zinc-800/50 border border-zinc-700/50 rounded-xl px-3 py-2.5 leading-relaxed">
                        {w}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Warnings */}
              {trace.warnings.length > 0 && (
                <section>
                  <SectionLabel icon={AlertTriangle} label="Warnings" />
                  <div className="flex flex-col gap-1.5">
                    {trace.warnings.map((w, i) => (
                      <div key={i} className="text-[12px] text-amber-300 bg-amber-950/30 border border-amber-800/40 rounded-xl px-3 py-2.5 leading-relaxed">
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
