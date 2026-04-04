import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  onSend: (content: string) => void;
  disabled: boolean;
  streaming: boolean;
}

export function ChatInput({ onSend, disabled, streaming }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

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
    <div className="px-4 pb-5 pt-3 bg-zinc-950 shrink-0">
      <div className="max-w-2xl mx-auto">
        <div className={cn(
          "flex items-end gap-3 bg-zinc-900 border rounded-2xl px-4 py-3",
          "transition-colors duration-100",
          "border-zinc-800 focus-within:border-zinc-600"
        )}>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? "Connecting…" : streaming ? "Responding…" : "Ask anything"}
            disabled={disabled}
            rows={1}
            className={cn(
              "flex-1 resize-none bg-transparent outline-none",
              "text-[14px] text-zinc-100 placeholder:text-zinc-600",
              "leading-relaxed min-h-[24px] max-h-[200px]",
              "disabled:opacity-40"
            )}
          />

          <motion.button
            onClick={handleSubmit}
            disabled={!canSend}
            whileTap={canSend ? { scale: 0.88 } : {}}
            className={cn(
              "shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-150",
              canSend
                ? "bg-amber-400 text-black cursor-pointer hover:bg-amber-300"
                : "bg-zinc-800 text-zinc-600 cursor-default"
            )}
          >
            <ArrowUp size={15} strokeWidth={2.5} />
          </motion.button>
        </div>

        <p className="text-center text-[11px] text-zinc-700 mt-2 select-none">
          Enter · send &nbsp;·&nbsp; Shift+Enter · newline
        </p>
      </div>
    </div>
  );
}
