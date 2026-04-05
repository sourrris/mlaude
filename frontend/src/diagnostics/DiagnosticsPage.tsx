import { ArrowLeft, Wifi, WifiOff } from "lucide-react";
import { useDiagnostics } from "./hooks/useDiagnostics";
import { StatsOverview } from "./components/StatsOverview";
import { DatePicker } from "./components/DatePicker";
import { TraceList } from "./components/TraceList";
import { TraceDetail } from "./components/TraceDetail";
import { ChromaDbPanel } from "./components/ChromaDbPanel";
import { SystemPanel } from "./components/SystemPanel";

export function DiagnosticsPage() {
  const {
    connected,
    traces,
    selectedTrace,
    setSelectedTrace,
    activeDate,
    availableDates,
    changeDate,
    chromaDb,
    systemInfo,
    stats,
  } = useDiagnostics();

  return (
    <div className="flex flex-col h-full bg-[#f9f8f6] text-zinc-800 font-sans overflow-hidden">
      {/* Top bar */}
      <header className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-zinc-200 bg-white">
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="flex items-center gap-1.5 text-[13px] text-zinc-500 hover:text-zinc-700 transition-colors"
          >
            <ArrowLeft size={14} />
            Chat
          </a>
          <div className="w-px h-4 bg-zinc-200" />
          <h1 className="text-[15px] font-semibold text-zinc-800">
            Diagnostics
          </h1>
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          {connected ? (
            <span className="flex items-center gap-1 text-emerald-600">
              <Wifi size={12} /> Connected
            </span>
          ) : (
            <span className="flex items-center gap-1 text-red-500">
              <WifiOff size={12} /> Disconnected
            </span>
          )}
        </div>
      </header>

      {/* Stats strip */}
      <div className="shrink-0 px-5 py-3 bg-[#f9f8f6]">
        <StatsOverview stats={stats} />
      </div>

      {/* Main content — two columns */}
      <div className="flex-1 flex min-h-0 px-5 pb-4 gap-4">
        {/* Left column — trace list */}
        <div className="w-[300px] shrink-0 flex flex-col bg-white border border-zinc-200 rounded-xl overflow-hidden">
          <div className="shrink-0 px-3 pt-3 pb-2">
            <DatePicker
              dates={availableDates}
              active={activeDate}
              onChange={changeDate}
            />
          </div>
          <div className="shrink-0 px-3 pb-2 border-b border-zinc-100">
            <p className="text-[11px] text-zinc-400">
              {traces.length} request{traces.length !== 1 ? "s" : ""}
            </p>
          </div>
          <TraceList
            traces={traces}
            selected={selectedTrace}
            onSelect={setSelectedTrace}
          />
        </div>

        {/* Right column — detail + health panels */}
        <div className="flex-1 flex flex-col min-w-0 gap-4">
          {/* Trace detail */}
          <div className="flex-1 bg-white border border-zinc-200 rounded-xl overflow-hidden flex flex-col min-h-0">
            <TraceDetail trace={selectedTrace} />
          </div>

          {/* Bottom health panels */}
          <div className="shrink-0 grid grid-cols-2 gap-4">
            <ChromaDbPanel chromaDb={chromaDb} />
            <SystemPanel systemInfo={systemInfo} />
          </div>
        </div>
      </div>
    </div>
  );
}
