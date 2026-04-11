import { Database } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChromaDbInfo } from "../types";

interface Props {
  chromaDb: ChromaDbInfo | null;
}

const SOURCE_DOT: Record<string, string> = {
  about: "bg-violet-400",
  interest: "bg-blue-400",
  behavior: "bg-emerald-400",
  general: "bg-zinc-400",
};

export function ChromaDbPanel({ chromaDb }: Props) {
  if (!chromaDb) {
    return (
      <div className="bg-white border border-zinc-200 rounded-xl p-4">
        <div className="flex items-center gap-1.5 mb-2">
          <Database size={13} className="text-zinc-400" />
          <span className="text-[12px] font-medium text-zinc-600">ChromaDB</span>
        </div>
        <p className="text-[12px] text-zinc-400 italic">Loading...</p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-zinc-200 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <Database size={13} className="text-zinc-400" />
          <span className="text-[12px] font-medium text-zinc-600">ChromaDB</span>
        </div>
        <span className="text-[11px] text-zinc-400">
          collection: <span className="font-mono text-zinc-600">{chromaDb.collection_name}</span>
        </span>
      </div>

      <div className="flex gap-4 mb-3">
        <div>
          <p className="text-[20px] font-semibold text-zinc-800 tabular-nums">
            {chromaDb.chunk_count}
          </p>
          <p className="text-[11px] text-zinc-400">chunks indexed</p>
        </div>
        <div>
          <p className="text-[20px] font-semibold text-zinc-800 tabular-nums">
            {chromaDb.knowledge_files.length}
          </p>
          <p className="text-[11px] text-zinc-400">knowledge files</p>
        </div>
      </div>

      {chromaDb.knowledge_files.length > 0 && (
        <div className="border-t border-zinc-100 pt-2 max-h-40 overflow-y-auto">
          {chromaDb.knowledge_files.map((f) => (
            <div
              key={f.path}
              className="flex items-center gap-2 py-1.5 text-[12px]"
            >
              <div
                className={cn(
                  "w-2 h-2 rounded-full shrink-0",
                  SOURCE_DOT[f.source_type] ?? SOURCE_DOT.general
                )}
              />
              <span className="text-zinc-600 truncate">{f.path}</span>
              <span className="text-[10px] text-zinc-400 shrink-0">
                {f.source_type}
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="text-[10px] text-zinc-400 mt-2 truncate">
        {chromaDb.knowledge_dir}
      </p>
    </div>
  );
}
