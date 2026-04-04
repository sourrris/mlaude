import { PanelLeftClose, PanelLeftOpen, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConnectionStatus, Trace } from "@/types";

interface Props {
  title: string | null;
  status: ConnectionStatus;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  trace: Trace | null;
  onOpenTrace: () => void;
}

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting:   "connecting",
  connected:    "online",
  disconnected: "offline",
};

const STATUS_COLOR: Record<ConnectionStatus, string> = {
  connecting:   "bg-yellow-500",
  connected:    "bg-emerald-500",
  disconnected: "bg-red-500",
};

export function TopBar({ title, status, sidebarOpen, onToggleSidebar, trace, onOpenTrace }: Props) {
  return (
    <header className="flex items-center gap-3 px-4 py-3 border-b border-[--color-border] bg-[--color-bg] min-h-[48px]">
      <button
        onClick={onToggleSidebar}
        className="p-1.5 rounded-[--radius-sm] text-[--color-text-3] hover:text-[--color-text] hover:bg-[--color-surface] transition-colors"
      >
        {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
      </button>

      <span className="flex-1 text-[13px] text-[--color-text-2] font-medium truncate text-center">
        {title ?? ""}
      </span>

      {/* Trace button — only shown when trace exists */}
      {trace && (
        <button
          onClick={onOpenTrace}
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1.5 rounded-[--radius-sm] text-[12px] font-medium",
            "text-[--color-text-3] hover:text-[--color-text-2] hover:bg-[--color-surface] transition-colors",
            trace.warnings.length > 0 && "text-yellow-500 hover:text-yellow-400"
          )}
        >
          <Activity size={13} />
          Trace
          {trace.warnings.length > 0 && (
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
          )}
        </button>
      )}

      {/* Connection status */}
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-[--color-surface] text-[11px] font-medium text-[--color-text-3]">
        <span className={cn("w-1.5 h-1.5 rounded-full", STATUS_COLOR[status])} />
        {STATUS_LABEL[status]}
      </div>
    </header>
  );
}
