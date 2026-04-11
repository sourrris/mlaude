import { Settings } from "lucide-react";
import type { SystemInfo } from "../types";

interface Props {
  systemInfo: SystemInfo | null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-zinc-50 last:border-0">
      <span className="text-[11px] text-zinc-400">{label}</span>
      <span className="text-[12px] font-mono text-zinc-700 text-right max-w-[60%] truncate">
        {value}
      </span>
    </div>
  );
}

export function SystemPanel({ systemInfo }: Props) {
  if (!systemInfo) {
    return (
      <div className="bg-white border border-zinc-200 rounded-xl p-4">
        <div className="flex items-center gap-1.5 mb-2">
          <Settings size={13} className="text-zinc-400" />
          <span className="text-[12px] font-medium text-zinc-600">System</span>
        </div>
        <p className="text-[12px] text-zinc-400 italic">Loading...</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-4">
      <div className="flex items-center gap-1.5 mb-3">
        <Settings size={13} className="text-zinc-400" />
        <span className="text-[12px] font-medium text-zinc-600">System</span>
      </div>

      <div className="flex flex-col">
        <Row label="Model" value={systemInfo.model} />
        <Row label="Embedding" value={systemInfo.embedding_model} />
        <Row label="Context limit" value={`${systemInfo.context_limit.toLocaleString()} tokens`} />
        <Row label="Ollama" value={systemInfo.ollama_url} />
        <Row
          label="Memory"
          value={`${(systemInfo.memory_size_bytes / 1024).toFixed(1)} KB (~${systemInfo.memory_tokens_approx} tokens)`}
        />
        <Row
          label="Knowledge"
          value={`${systemInfo.knowledge_file_count} files`}
        />
        <Row label="Home" value={systemInfo.mlaude_home} />
      </div>
    </div>
  );
}
