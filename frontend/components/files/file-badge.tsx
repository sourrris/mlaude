import { FileText, X } from "lucide-react";

import type { WorkspaceFile } from "@/lib/types";

interface FileBadgeProps {
  file: WorkspaceFile;
  onRemove?: (fileId: string) => void;
}

export function FileBadge({ file, onRemove }: FileBadgeProps) {
  return (
    <div className="flex max-w-full items-center gap-2 rounded-2xl border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] px-3 py-2 text-sm text-[color:var(--text-main)]">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[color:var(--accent-soft)] text-[color:var(--accent)]">
        <FileText size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{file.title}</p>
        <p className="truncate text-xs text-[color:var(--text-faint)]">
          {file.filename}
        </p>
      </div>
      {onRemove ? (
        <button
          type="button"
          onClick={() => onRemove(file.id)}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[color:var(--text-faint)] transition hover:bg-white hover:text-[color:var(--text-main)]"
          aria-label={`Remove ${file.filename}`}
        >
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}
