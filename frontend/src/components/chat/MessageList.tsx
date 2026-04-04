import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { Message } from "@/types";

interface Props {
  messages: Message[];
  streaming: boolean;
  streamingContent: string;
  activeToolName: string | null;
}

function parseMarkdown(text: string): string {
  return text
    // Code blocks
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="lang-${lang}">${escapeHtml(code.trim())}</code></pre>`
    )
    // Inline code
    .replace(/`([^`]+)`/g, (_, code) => `<code>${escapeHtml(code)}</code>`)
    // Bold
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    // Headers
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    // Horizontal rule
    .replace(/^---$/gm, "<hr>")
    // Blockquote
    .replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>")
    // Unordered list
    .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
    // Ordered list
    .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    // Paragraphs (double newlines)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>")
    // Single newlines inside paragraphs
    .replace(/\n/g, "<br>");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function StreamingCursor() {
  return (
    <motion.span
      className="inline-block w-[2px] h-[14px] ml-0.5 rounded-full bg-[--color-accent] align-middle"
      animate={{ opacity: [1, 0, 1] }}
      transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}

function ToolBadge({ name }: { name: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2 py-1.5 px-3 rounded-[--radius-sm] bg-[--color-surface-2] border border-[--color-border] w-fit text-[12px] text-[--color-text-3]"
    >
      <motion.div
        className="w-1.5 h-1.5 rounded-full bg-[--color-accent]"
        animate={{ opacity: [1, 0.3, 1] }}
        transition={{ duration: 1, repeat: Infinity }}
      />
      {name}…
    </motion.div>
  );
}

export function MessageList({ messages, streaming, streamingContent, activeToolName }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const isEmpty = messages.length === 0 && !streaming;

  return (
    <div className="flex-1 overflow-y-auto">
      {isEmpty ? (
        <div className="h-full flex flex-col items-center justify-center gap-3 px-8 text-center">
          <div className="w-10 h-10 rounded-xl bg-[--color-surface-2] border border-[--color-border] flex items-center justify-center">
            <span className="text-[--color-accent] text-lg font-semibold">m</span>
          </div>
          <p className="text-[--color-text-2] text-[14px] max-w-xs leading-relaxed">
            What are you thinking about?
          </p>
        </div>
      ) : (
        <div className="max-w-[720px] w-full mx-auto px-6 py-8 flex flex-col gap-8">
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                className={cn(
                  "flex flex-col gap-1.5",
                  msg.role === "user" ? "items-end" : "items-start"
                )}
              >
                <span className={cn(
                  "text-[11px] font-medium tracking-wide uppercase",
                  msg.role === "user" ? "text-[--color-text-3]" : "text-[--color-accent]"
                )}>
                  {msg.role === "user" ? "you" : "mlaude"}
                </span>

                {msg.role === "user" ? (
                  <div className="bg-[--color-user-bg] border border-[--color-border] rounded-[--radius-lg] rounded-br-[--radius-sm] px-4 py-3 text-[14px] text-[--color-text] max-w-[85%] whitespace-pre-wrap leading-relaxed">
                    {msg.content}
                  </div>
                ) : (
                  <div
                    className="prose-message text-[14px] max-w-full"
                    dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
                  />
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Tool call indicator */}
          {activeToolName && (
            <div className="flex flex-col gap-1.5 items-start">
              <span className="text-[11px] font-medium tracking-wide uppercase text-[--color-accent]">
                mlaude
              </span>
              <ToolBadge name={activeToolName} />
            </div>
          )}

          {/* Streaming assistant message */}
          {streaming && streamingContent && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col gap-1.5 items-start"
            >
              <span className="text-[11px] font-medium tracking-wide uppercase text-[--color-accent]">
                mlaude
              </span>
              <div className="prose-message text-[14px] max-w-full">
                <span dangerouslySetInnerHTML={{ __html: parseMarkdown(streamingContent) }} />
                <StreamingCursor />
              </div>
            </motion.div>
          )}

          {/* Streaming with no content yet (thinking) */}
          {streaming && !streamingContent && !activeToolName && (
            <div className="flex flex-col gap-1.5 items-start">
              <span className="text-[11px] font-medium tracking-wide uppercase text-[--color-accent]">
                mlaude
              </span>
              <div className="flex items-center gap-1 py-1">
                {[0, 0.15, 0.3].map((delay, i) => (
                  <motion.div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[--color-text-3]"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1, repeat: Infinity, delay }}
                  />
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
