import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
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

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled || streaming) return;
    onSend(trimmed);
    setValue("");
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
    <div className="px-4 pb-4 pt-3 border-t border-[--color-border] bg-[--color-bg]">
      <div className="max-w-[720px] mx-auto">
        <div className={cn(
          "flex items-end gap-3 bg-[--color-surface] border rounded-[--radius-lg] px-4 py-3",
          "transition-colors duration-[--duration-fast]",
          "border-[--color-border] focus-within:border-[--color-border-2]"
        )}>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={streaming ? "Thinking…" : "Message mlaude"}
            disabled={disabled}
            rows={1}
            className={cn(
              "flex-1 resize-none bg-transparent outline-none text-[14px]",
              "text-[--color-text] placeholder:text-[--color-text-3]",
              "leading-relaxed min-h-[24px] max-h-[200px]",
              "disabled:opacity-50"
            )}
          />

          <motion.button
            onClick={handleSubmit}
            disabled={!canSend && !streaming}
            whileTap={{ scale: 0.92 }}
            className={cn(
              "shrink-0 w-8 h-8 rounded-[--radius-sm] flex items-center justify-center",
              "transition-all duration-[--duration-fast]",
              canSend || streaming
                ? "bg-[--color-accent] text-black cursor-pointer"
                : "bg-[--color-surface-2] text-[--color-text-3] cursor-default"
            )}
          >
            {streaming ? <Square size={13} fill="currentColor" /> : <ArrowUp size={15} strokeWidth={2.5} />}
          </motion.button>
        </div>

        <p className="text-center text-[11px] text-[--color-text-3] mt-2">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
