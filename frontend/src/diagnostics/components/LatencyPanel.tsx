import { Clock } from "lucide-react";
import type { DiagTrace } from "../types";

interface Props {
  trace: DiagTrace;
}

function Bar({ label, ms, maxMs }: { label: string; ms: number; maxMs: number }) {
  const pct = maxMs > 0 ? Math.min((ms / maxMs) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-[11px] text-zinc-500 w-24 shrink-0 text-right">
        {label}
      </span>
      <div className="flex-1 h-5 bg-zinc-100 rounded overflow-hidden">
        <div
          className="h-full bg-[#d97757]/70 rounded transition-all"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
      <span className="text-[11px] font-mono text-zinc-600 tabular-nums w-16 shrink-0">
        {ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`}
      </span>
    </div>
  );
}

export function LatencyPanel({ trace }: Props) {
  const allDurations = [
    trace.first_token_ms,
    trace.total_ms,
    ...(trace.rag ? [trace.rag.duration_ms] : []),
    ...(trace.tool_calls ?? []).map((tc) => tc.duration_ms),
  ];
  const maxMs = Math.max(...allDurations, 1);

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-3">
        <Clock size={13} className="text-zinc-400" />
        <span className="text-[12px] font-medium text-zinc-600">
          Latency breakdown
        </span>
      </div>
      <div className="flex flex-col gap-2">
        <Bar label="First token" ms={trace.first_token_ms ?? 0} maxMs={maxMs} />
        <Bar label="Total" ms={trace.total_ms ?? 0} maxMs={maxMs} />
        {trace.rag && (
          <Bar label="RAG query" ms={trace.rag.duration_ms} maxMs={maxMs} />
        )}
        {(trace.tool_calls ?? []).map((tc, i) => (
          <Bar
            key={i}
            label={tc.name}
            ms={tc.duration_ms}
            maxMs={maxMs}
          />
        ))}
      </div>
    </div>
  );
}
