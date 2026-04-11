import { AlertTriangle } from "lucide-react";
import type { DiagTrace } from "../types";

interface Props {
  trace: DiagTrace;
}

export function WarningsBanner({ trace }: Props) {
  const warnings = trace.warnings ?? [];
  if (warnings.length === 0) return null;

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <AlertTriangle size={13} className="text-amber-500" />
        <span className="text-[12px] font-medium text-amber-700">
          Warnings ({warnings.length})
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {warnings.map((w, i) => (
          <div
            key={i}
            className="text-[12px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 leading-relaxed"
          >
            {w}
          </div>
        ))}
      </div>
    </div>
  );
}
