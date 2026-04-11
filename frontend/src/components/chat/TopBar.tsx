import { PanelLeftClose, PanelLeftOpen, Activity, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState } from "react";
import type { ConnectionStatus, Trace } from "@/types";

interface Props {
  title: string | null;
  status: ConnectionStatus;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  trace: Trace | null;
  onOpenTrace: () => void;
}

interface Props {
  title: string | null;
  status: ConnectionStatus;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  trace: Trace | null;
  onOpenTrace: () => void;
  models: string[];
  currentModel: string;
  onModelChange: (model: string) => void;
}

export function TopBar({ title, status, sidebarOpen, onToggleSidebar, trace, onOpenTrace, models, currentModel, onModelChange }: Props) {
  const isOnline = status === "connected";
  const isConnecting = status === "connecting";
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);

  return (
    <header className="flex items-center gap-3 px-4 h-14 border-b border-zinc-100 bg-white shrink-0 top-0 sticky z-20">
      <button
        onClick={onToggleSidebar}
        className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors duration-100"
        title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
      >
        {sidebarOpen
          ? <PanelLeftClose size={18} />
          : <PanelLeftOpen size={18} />
        }
      </button>

      <span className="flex-1 text-[13px] font-medium text-zinc-600 truncate text-center">
        {title ?? "New chat"}
      </span>

      {/* Model selector */}
      <div className="relative">
        <button
          onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-zinc-200 bg-zinc-50 text-zinc-700 hover:bg-zinc-100 transition-colors duration-100"
        >
          <span className="text-[12px]">{currentModel.split(':')[0]}</span>
          <ChevronDown size={14} className={isModelDropdownOpen ? "text-zinc-700 rotate-180" : "text-zinc-500"} />
        </button>
        
        {/* Model dropdown */}
        {isModelDropdownOpen && (
          <div className="absolute top-full mt-2 w-56 rounded-md bg-white border border-zinc-200 shadow-lg z-20">
            <div className="py-1">
              {models.map((model) => (
                <button
                  key={model}
                  onClick={() => {
                    setIsModelDropdownOpen(false);
                    onModelChange(model);
                  }}
                  className={`flex w-full px-4 py-2 text-sm text-left ${
                    model === currentModel
                      ? "bg-emerald-50 text-emerald-700"
                      : "hover:bg-zinc-50"
                  }`}
                >
                  {model.split(':')[0]}
                  {model === currentModel && (
                    <span className="ml-auto text-xs text-emerald-500">
                      ✓
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Trace button */}
      {trace && (
        <button
          onClick={onOpenTrace}
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[12px] font-medium transition-colors duration-100",
            trace.warnings.length > 0
              ? "text-[#d97757] bg-orange-50 hover:bg-orange-100"
              : "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100"
          )}
        >
          <Activity size={14} />
          <span>Trace</span>
          {trace.warnings.length > 0 && (
            <span className="w-1.5 h-1.5 rounded-full bg-[#d97757]" />
          )}
        </button>
      )}

      {/* Status pill */}
      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-50 border border-zinc-200">
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
