"use client";

import { useEffect, useRef } from "react";
import { ArrowUp, Paperclip, Square } from "lucide-react";

import { FileBadge } from "@/components/files/file-badge";
import type { WorkspaceFile } from "@/lib/types";

interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  draftFiles: WorkspaceFile[];
  onRemoveFile: (fileId: string) => void;
  onUploadFiles: (files: File[]) => void;
  models: string[];
  selectedModel: string;
  onModelChange: (value: string) => void;
  disabled?: boolean;
  streaming?: boolean;
}

export function ChatInputBar({
  value,
  onChange,
  onSubmit,
  onStop,
  draftFiles,
  onRemoveFile,
  onUploadFiles,
  models,
  selectedModel,
  onModelChange,
  disabled = false,
  streaming = false,
}: ChatInputBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    element.style.height = "0px";
    element.style.height = `${Math.min(element.scrollHeight, 220)}px`;
  }, [value]);

  return (
    <div className="panel-surface rounded-[1.75rem] p-4">
      {draftFiles.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {draftFiles.map((file) => (
            <FileBadge key={file.id} file={file} onRemove={onRemoveFile} />
          ))}
        </div>
      ) : null}

      <div className="flex items-end gap-3">
        <div className="min-w-0 flex-1 rounded-[1.5rem] border border-[color:var(--border-soft)] bg-white px-4 py-3 shadow-sm">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            data-testid="chat-composer"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (streaming) {
                  return;
                }
                onSubmit();
              }
            }}
            placeholder={
              disabled
                ? "Workspace unavailable"
                : streaming
                  ? "Streaming response…"
                  : "Chat with mlaude"
            }
            className="max-h-[220px] min-h-[28px] w-full resize-none bg-transparent text-[15px] leading-7 text-[color:var(--text-main)] outline-none placeholder:text-[color:var(--text-faint)]"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-[color:var(--border-soft)] bg-white text-[color:var(--text-soft)] transition hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-main)]"
                aria-label="Attach files"
              >
                <Paperclip size={16} />
              </button>

              {models.length > 0 && (
                <div className="relative">
                  <select
                    value={selectedModel}
                    onChange={(e) => onModelChange(e.target.value)}
                    data-testid="composer-model-select"
                    className="h-11 appearance-none rounded-2xl border border-[color:var(--border-soft)] bg-white pl-4 pr-10 text-sm font-medium text-[color:var(--text-soft)] outline-none transition hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-main)] focus:border-[color:var(--accent)]"
                  >
                    {models.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                  <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[color:var(--text-faint)]">
                    <svg
                      width="10"
                      height="6"
                      viewBox="0 0 10 6"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M1 1L5 5L9 1"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                </div>
              )}
            </div>
            <div className="flex items-center justify-end gap-3">
              <p className="text-xs text-[color:var(--text-faint)]">
                Enter to send, Shift+Enter for a new line
              </p>
              <button
                type="button"
                onClick={streaming ? onStop : onSubmit}
                disabled={disabled || (!streaming && !value.trim())}
                data-testid="composer-submit"
                className={`flex h-11 w-11 items-center justify-center rounded-2xl text-white transition ${
                  streaming
                    ? "bg-[color:var(--warning)] hover:opacity-90"
                    : value.trim() && !disabled
                      ? "bg-[color:var(--accent)] hover:opacity-90"
                      : "bg-stone-300"
                }`}
                aria-label={streaming ? "Stop response" : "Send message"}
              >
                {streaming ? (
                  <Square size={14} fill="currentColor" />
                ) : (
                  <ArrowUp size={17} />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        data-testid="composer-file-input"
        onChange={(event) => {
          const files = event.target.files
            ? Array.from(event.target.files)
            : [];
          if (files.length) {
            onUploadFiles(files);
            event.target.value = "";
          }
        }}
      />
    </div>
  );
}
