import { ContextBar } from "./ContextBar";
import { LatencyPanel } from "./LatencyPanel";
import { RagPanel } from "./RagPanel";
import { ToolCallPanel } from "./ToolCallPanel";
import { WarningsBanner } from "./WarningsBanner";
import type { DiagTrace } from "../types";

interface Props {
  trace: DiagTrace | null;
}

export function TraceDetail({ trace }: Props) {
  if (!trace) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-[14px] text-zinc-400">Select a trace to inspect</p>
          <p className="text-[12px] text-zinc-300 mt-1">
            Click any request in the list
          </p>
        </div>
      </div>
    );
  }

  const ts = trace.ts
    ? new Date(trace.ts).toLocaleString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <div className="flex-1 overflow-y-auto p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-[14px] font-semibold text-zinc-800">
            Request trace
          </h3>
          <div className="flex items-center gap-3 mt-0.5 text-[11px] text-zinc-400">
            {trace.request_id && (
              <span className="font-mono">{trace.request_id}</span>
            )}
            {ts && <span>{ts}</span>}
            {trace.session_id && (
              <span>session:{trace.session_id.slice(0, 8)}</span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <div className="text-center bg-zinc-50 border border-zinc-200 rounded-lg px-3 py-1.5">
            <p className="text-[14px] font-semibold text-zinc-800 tabular-nums">
              {trace.total_ms < 1000
                ? `${trace.total_ms}ms`
                : `${(trace.total_ms / 1000).toFixed(1)}s`}
            </p>
            <p className="text-[10px] text-zinc-400">total</p>
          </div>
          <div className="text-center bg-zinc-50 border border-zinc-200 rounded-lg px-3 py-1.5">
            <p className="text-[14px] font-semibold text-zinc-800 tabular-nums">
              {trace.first_token_ms}ms
            </p>
            <p className="text-[10px] text-zinc-400">TTFT</p>
          </div>
          <div className="text-center bg-zinc-50 border border-zinc-200 rounded-lg px-3 py-1.5">
            <p className="text-[14px] font-semibold text-zinc-800 tabular-nums">
              {trace.response_tokens}
            </p>
            <p className="text-[10px] text-zinc-400">tokens out</p>
          </div>
        </div>
      </div>

      {/* Panels */}
      <div className="flex flex-col gap-6">
        <WarningsBanner trace={trace} />
        <ContextBar trace={trace} />
        <LatencyPanel trace={trace} />
        <RagPanel trace={trace} />
        <ToolCallPanel trace={trace} />

        {/* Memory writes */}
        {(trace.memory_writes ?? []).length > 0 && (
          <div>
            <p className="text-[12px] font-medium text-zinc-600 mb-2">
              Memory writes ({trace.memory_writes.length})
            </p>
            <div className="flex flex-col gap-1.5">
              {trace.memory_writes.map((w, i) => (
                <div
                  key={i}
                  className="text-[12px] text-zinc-600 bg-zinc-50 border border-zinc-200 rounded-lg px-3 py-2.5 leading-relaxed"
                >
                  {w}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
