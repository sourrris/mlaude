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

export function TopBar({ title, status, sidebarOpen, onToggleSidebar, trace, onOpenTrace }: Props) {
  const isOnline = status === "connected";
  const isConnecting = status === "connecting";

  return (
    <header className="flex items-center gap-3 px-4 h-12 border-b border-zinc-800 bg-zinc-950 shrink-0">
      <button
        onClick={onToggleSidebar}
        className="p-1.5 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors duration-100"
        title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
      >
        {sidebarOpen
          ? <PanelLeftClose size={15} />
          : <PanelLeftOpen size={15} />
        }
      </button>

      <span className="flex-1 text-[13px] text-zinc-500 truncate text-center">
        {title ?? ""}
      </span>

      {/* Trace button */}
      {trace && (
        <button
          onClick={onOpenTrace}
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] font-medium transition-colors duration-100",
            trace.warnings.length > 0
              ? "text-amber-400 hover:bg-amber-400/10"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
          )}
        >
          <Activity size={13} />
          <span>Trace</span>
          {trace.warnings.length > 0 && (
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          )}
        </button>
      )}

      {/* Status pill */}
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-900 border border-zinc-800">
        <span className={cn(
          "w-1.5 h-1.5 rounded-full",
          isOnline ? "bg-emerald-500" :
          isConnecting ? "bg-amber-400 animate-pulse" :
          "bg-red-500"
        )} />
        <span className="text-[11px] font-medium text-zinc-500">
          {isOnline ? "online" : isConnecting ? "connecting" : "offline"}
        </span>
      </div>
    </header>
  );
}
