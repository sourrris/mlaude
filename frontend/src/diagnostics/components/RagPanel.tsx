import { Database } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DiagTrace } from "../types";

interface Props {
  trace: DiagTrace;
}

const SOURCE_BADGE: Record<string, string> = {
  about: "text-violet-700 bg-violet-50 border-violet-200",
  interest: "text-blue-700 bg-blue-50 border-blue-200",
  behavior: "text-emerald-700 bg-emerald-50 border-emerald-200",
  general: "text-zinc-600 bg-zinc-50 border-zinc-200",
};

export function RagPanel({ trace }: Props) {
  if (!trace.rag) {
    return (
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <Database size={13} className="text-zinc-400" />
          <span className="text-[12px] font-medium text-zinc-600">RAG</span>
        </div>
        <p className="text-[12px] text-zinc-400 italic">
          No RAG query for this request
        </p>
      </div>
    );
  }

  const { rag } = trace;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <Database size={13} className="text-zinc-400" />
          <span className="text-[12px] font-medium text-zinc-600">
            RAG pipeline
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-zinc-400">
          <span>
            <span className="font-semibold text-zinc-600">{rag.count}</span>{" "}
            chunks
          </span>
          <span>
            <span className="font-semibold text-zinc-600">{rag.duration_ms}</span>
            ms
          </span>
          {rag.rag_tokens != null && (
            <span>
              ~<span className="font-semibold text-zinc-600">{rag.rag_tokens}</span>{" "}
              tokens
            </span>
          )}
        </div>
      </div>

      {/* Query */}
      <div className="bg-zinc-50 border border-zinc-200 rounded-lg px-3 py-2 mb-3">
        <p className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider mb-1">
          Query
        </p>
        <p className="text-[12px] text-zinc-700 leading-relaxed">{rag.query}</p>
      </div>

      {/* Chunks */}
      {(rag.chunks ?? []).length === 0 ? (
        <p className="text-[12px] text-zinc-400 italic">
          No chunks matched threshold
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {(rag.chunks ?? []).map((chunk, i) => (
            <div
              key={i}
              className="bg-white border border-zinc-200 rounded-lg p-3"
            >
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <span
                  className={cn(
                    "text-[10px] font-medium px-1.5 py-0.5 rounded border",
                    SOURCE_BADGE[chunk.source_type] ?? SOURCE_BADGE.general
                  )}
                >
                  {chunk.source_type}
                </span>
                <span className="text-[11px] text-zinc-400 truncate flex-1 min-w-0">
                  {chunk.source}
                </span>
                <span className="text-[11px] font-mono text-zinc-500 tabular-nums shrink-0">
                  {chunk.score.toFixed(3)}
                </span>
              </div>
              <p className="text-[12px] text-zinc-500 leading-relaxed line-clamp-3">
                {chunk.preview}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
