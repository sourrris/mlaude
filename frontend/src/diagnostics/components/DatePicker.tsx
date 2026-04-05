import { cn } from "@/lib/utils";

interface Props {
  dates: string[];
  active: string;
  onChange: (date: string) => void;
}

export function DatePicker({ dates, active, onChange }: Props) {
  if (dates.length === 0) return null;

  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1">
      {dates.map((d) => (
        <button
          key={d}
          onClick={() => onChange(d)}
          className={cn(
            "shrink-0 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors",
            d === active
              ? "bg-zinc-800 text-white"
              : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700"
          )}
        >
          {d}
        </button>
      ))}
    </div>
  );
}
