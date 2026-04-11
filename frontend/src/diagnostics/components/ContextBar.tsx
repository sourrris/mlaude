import { cn } from "@/lib/utils";
import type { DiagTrace } from "../types";

interface Props {
  trace: DiagTrace;
}

interface Segment {
  label: string;
  tokens: number;
  color: string;
}

export function ContextBar({ trace }: Props) {
  const limit = trace.context_limit ?? 32768;
  const sysTokens = trace.system_prompt_tokens ?? 0;
  const memTokens = trace.memory_tokens ?? 0;
  const ragTokens = trace.rag?.rag_tokens ?? 0;
  const responseTokens = trace.response_tokens ?? 0;

  // History tokens = total context - system - memory - rag (approximate)
  const historyTokens = Math.max(
    0,
    trace.context_tokens - sysTokens - memTokens - ragTokens
  );

  const segments: Segment[] = [
    { label: "System", tokens: sysTokens, color: "bg-violet-400" },
    { label: "History", tokens: historyTokens, color: "bg-blue-400" },
    { label: "Memory", tokens: memTokens, color: "bg-emerald-400" },
    { label: "RAG", tokens: ragTokens, color: "bg-amber-400" },
    { label: "Response", tokens: responseTokens, color: "bg-zinc-400" },
  ].filter((s) => s.tokens > 0);

  const totalUsed = trace.context_tokens + responseTokens;
  const remaining = Math.max(0, limit - totalUsed);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[12px] font-medium text-zinc-600">
          Context window
        </span>
        <span
          className={cn(
            "text-[12px] font-semibold tabular-nums",
            trace.context_pct >= 90
              ? "text-red-600"
              : trace.context_pct >= 70
                ? "text-amber-600"
                : "text-emerald-600"
          )}
        >
          {trace.context_tokens.toLocaleString()} / {limit.toLocaleString()} tokens ({trace.context_pct}%)
        </span>
      </div>

      {/* Stacked bar */}
      <div className="h-3 bg-zinc-100 rounded-full overflow-hidden flex">
        {segments.map((seg) => {
          const pct = (seg.tokens / limit) * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={seg.label}
              className={cn("h-full transition-all", seg.color)}
              style={{ width: `${Math.min(pct, 100)}%` }}
              title={`${seg.label}: ${seg.tokens.toLocaleString()} tokens`}
            />
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1.5">
            <div className={cn("w-2 h-2 rounded-full", seg.color)} />
            <span className="text-[11px] text-zinc-500">
              {seg.label}:{" "}
              <span className="font-medium text-zinc-700 tabular-nums">
                {seg.tokens.toLocaleString()}
              </span>
            </span>
          </div>
        ))}
        {remaining > 0 && (
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-zinc-200" />
            <span className="text-[11px] text-zinc-500">
              Remaining:{" "}
              <span className="font-medium text-zinc-700 tabular-nums">
                {remaining.toLocaleString()}
              </span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
