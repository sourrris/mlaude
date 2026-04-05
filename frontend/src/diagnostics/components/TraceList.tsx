import { cn } from "@/lib/utils";
import { AlertTriangle, Wrench } from "lucide-react";
import type { DiagTrace } from "../types";

interface Props {
  traces: DiagTrace[];
  selected: DiagTrace | null;
  onSelect: (trace: DiagTrace) => void;
}

function formatTime(ts?: string): string {
  if (!ts) return "--:--";
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return ts.slice(11, 19);
  }
}

function pctColor(pct: number): string {
  if (pct >= 90) return "text-red-600 bg-red-50 border-red-200";
  if (pct >= 70) return "text-amber-600 bg-amber-50 border-amber-200";
  return "text-emerald-600 bg-emerald-50 border-emerald-200";
}

export function TraceList({ traces, selected, onSelect }: Props) {
  if (traces.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-[13px] text-zinc-400">No traces found</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="flex flex-col gap-1 p-2">
        {traces.map((t, i) => {
          const isSelected = selected?.request_id === t.request_id && selected?.ts === t.ts;
          return (
            <button
              key={t.request_id ?? i}
              onClick={() => onSelect(t)}
              className={cn(
                "w-full text-left px-3 py-2.5 rounded-xl transition-colors",
                isSelected
                  ? "bg-zinc-100 border border-zinc-300"
                  : "hover:bg-zinc-50 border border-transparent"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] font-mono text-zinc-500 tabular-nums">
                  {formatTime(t.ts)}
                </span>
                <div className="flex items-center gap-1.5">
                  {(t.tool_calls ?? []).length > 0 && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] text-zinc-500">
                      <Wrench size={10} />
                      {t.tool_calls.length}
                    </span>
                  )}
                  {(t.warnings ?? []).length > 0 && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] text-amber-500">
                      <AlertTriangle size={10} />
                      {t.warnings.length}
                    </span>
                  )}
                  <span
                    className={cn(
                      "text-[10px] font-semibold px-1.5 py-0.5 rounded border",
                      pctColor(t.context_pct)
                    )}
                  >
                    {t.context_pct}%
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between gap-2 mt-1">
                <span className="text-[11px] text-zinc-400 truncate">
                  {t.session_id ? `session:${t.session_id.slice(0, 8)}` : ""}
                </span>
                <span className="text-[11px] text-zinc-400 tabular-nums shrink-0">
                  {t.total_ms < 1000
                    ? `${t.total_ms}ms`
                    : `${(t.total_ms / 1000).toFixed(1)}s`}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
