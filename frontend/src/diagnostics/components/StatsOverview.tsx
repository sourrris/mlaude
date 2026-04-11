import { Activity, Clock, Gauge, Wrench, AlertTriangle, Database } from "lucide-react";
import type { DiagStats } from "../types";

interface Props {
  stats: DiagStats | null;
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="flex items-center gap-3 bg-white border border-zinc-200 rounded-xl px-4 py-3 min-w-0">
      <div className="shrink-0 w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center">
        <Icon size={16} className="text-zinc-500" />
      </div>
      <div className="min-w-0">
        <p className="text-[18px] font-semibold text-zinc-800 leading-tight tabular-nums">
          {value}
        </p>
        <p className="text-[11px] text-zinc-400 leading-tight mt-0.5">{label}</p>
        {sub && (
          <p className="text-[10px] text-zinc-400 leading-tight">{sub}</p>
        )}
      </div>
    </div>
  );
}

export function StatsOverview({ stats }: Props) {
  if (!stats || stats.request_count === 0) {
    return (
      <div className="grid grid-cols-3 gap-3">
        <StatCard icon={Activity} label="Requests" value="0" />
        <StatCard icon={Clock} label="Avg latency" value="--" />
        <StatCard icon={Gauge} label="Avg context" value="--" />
      </div>
    );
  }

  const toolTotal = Object.values(stats.tool_call_counts ?? {}).reduce(
    (a, b) => a + b,
    0
  );

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <StatCard
        icon={Activity}
        label="Requests today"
        value={String(stats.request_count)}
      />
      <StatCard
        icon={Clock}
        label="Avg latency"
        value={`${((stats.avg_total_ms ?? 0) / 1000).toFixed(1)}s`}
        sub={`TTFT: ${stats.avg_first_token_ms ?? 0}ms`}
      />
      <StatCard
        icon={Gauge}
        label="Avg context"
        value={`${stats.avg_context_pct ?? 0}%`}
      />
      <StatCard
        icon={Wrench}
        label="Tool calls"
        value={String(toolTotal)}
      />
      <StatCard
        icon={Database}
        label="RAG avg"
        value={`${stats.rag_avg_duration_ms ?? 0}ms`}
        sub={`~${stats.rag_avg_chunks ?? 0} chunks`}
      />
      <StatCard
        icon={AlertTriangle}
        label="Warnings"
        value={String(stats.warning_count ?? 0)}
      />
    </div>
  );
}
