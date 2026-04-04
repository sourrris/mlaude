import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  onSend: (content: string) => void;
  disabled: boolean;
  streaming: boolean;
}

export function ChatInput({ onSend, disabled, streaming }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [value]);

  // Re-focus after streaming ends
  useEffect(() => {
    if (!streaming) textareaRef.current?.focus();
  }, [streaming]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled || streaming) return;
    onSend(trimmed);
    setValue("");
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [value, disabled, streaming, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  const canSend = value.trim().length > 0 && !disabled && !streaming;

  return (
    <div className="w-full max-w-3xl mx-auto px-4 pb-4 pt-1">
      {/* Elevated pill — Claude-style */}
      <div
        className={cn(
          "relative flex flex-col bg-white rounded-2xl",
          "shadow-[0_0_0_1px_rgba(0,0,0,0.08),0_2px_20px_rgba(0,0,0,0.08)]",
          "transition-shadow duration-200",
          "focus-within:shadow-[0_0_0_1.5px_rgba(0,0,0,0.12),0_4px_24px_rgba(0,0,0,0.12)]"
        )}
      >
        {/* Textarea */}
        <div className="px-4 pt-3.5 pb-2">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              disabled ? "Connecting…" : streaming ? "Responding…" : "Reply to mlaude…"
            }
            disabled={disabled || streaming}
            rows={1}
            className={cn(
              "w-full resize-none bg-transparent outline-none",
              "text-[15px] text-zinc-800 placeholder:text-zinc-400",
              "leading-[1.6] min-h-6.5 max-h-60",
              "disabled:opacity-50 disabled:cursor-default"
            )}
          />
        </div>

        {/* Bottom action row */}
        <div className="flex items-center justify-between px-3 pb-2.5">
          <span className="text-[11px] text-zinc-400 pl-1 select-none">
            {streaming ? "Streaming…" : "Shift↵ new line"}
          </span>

          <button
            onClick={handleSubmit}
            disabled={!canSend && !streaming}
            aria-label={streaming ? "Stop" : "Send"}
            className={cn(
              "shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
              "transition-all duration-150",
              canSend
                ? "bg-zinc-900 text-white cursor-pointer hover:bg-zinc-700 active:scale-90"
                : streaming
                ? "bg-zinc-200 text-zinc-600 cursor-pointer hover:bg-zinc-300 active:scale-90"
                : "bg-zinc-100 text-zinc-300 cursor-default"
            )}
          >
            {streaming ? <Square size={12} fill="currentColor" /> : <ArrowUp size={15} strokeWidth={2.5} />}
          </button>
        </div>
      </div>

      <p className="text-center text-[11px] text-zinc-400 mt-2 select-none">
        mlaude may make mistakes
      </p>
    </div>
  );
}
