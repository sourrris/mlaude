import { useState } from "react";
import { Wrench, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DiagTrace } from "../types";

interface Props {
  trace: DiagTrace;
}

function ToolRow({ tc }: { tc: DiagTrace["tool_calls"][number] }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        "border rounded-lg overflow-hidden",
        tc.error ? "border-red-200 bg-red-50/50" : "border-zinc-200 bg-white"
      )}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left hover:bg-zinc-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDown size={12} className="text-zinc-400" />
          ) : (
            <ChevronRight size={12} className="text-zinc-400" />
          )}
          <span className="text-[13px] font-mono text-zinc-700">{tc.name}</span>
          {tc.error && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-100 text-red-600 border border-red-200">
              ERROR
            </span>
          )}
        </div>
        <span className="text-[11px] font-mono text-zinc-400 tabular-nums">
          {tc.duration_ms}ms
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 border-t border-zinc-100">
          {/* Args */}
          <div className="mt-2">
            <p className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider mb-1">
              Input
            </p>
            <pre className="text-[11px] font-mono text-zinc-600 bg-zinc-50 border border-zinc-200 rounded-md p-2 overflow-x-auto max-h-32">
              {JSON.stringify(tc.args, null, 2)}
            </pre>
          </div>

          {/* Result */}
          {tc.result_preview && (
            <div className="mt-2">
              <p className="text-[10px] font-medium text-zinc-400 uppercase tracking-wider mb-1">
                Output
              </p>
              <pre
                className={cn(
                  "text-[11px] font-mono rounded-md p-2 overflow-x-auto max-h-40 border",
                  tc.error
                    ? "text-red-600 bg-red-50 border-red-200"
                    : "text-zinc-600 bg-zinc-50 border-zinc-200"
                )}
              >
                {tc.result_preview}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ToolCallPanel({ trace }: Props) {
  const calls = trace.tool_calls ?? [];
  if (calls.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-3">
        <Wrench size={13} className="text-zinc-400" />
        <span className="text-[12px] font-medium text-zinc-600">
          Tool calls ({calls.length})
        </span>
      </div>
      <div className="flex flex-col gap-2">
        {calls.map((tc, i) => (
          <ToolRow key={i} tc={tc} />
        ))}
      </div>
    </div>
  );
}
