import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
import type { Message } from "@/types";
import { ThinkingBlock } from "./ThinkingBlock";

interface Props {
  messages: Message[];
  streaming: boolean;
  streamingContent: string;
  streamingThinking: boolean;
  thinkingContent: string;
  thinkingDuration: number | null;
  activeToolName: string | null;
  isEmpty: boolean;
}

function StreamingCursor() {
  return (
    <motion.span
      className="inline-block w-[2px] h-[15px] ml-0.5 rounded-full bg-[#d97757] align-text-bottom"
      animate={{ opacity: [1, 0] }}
      transition={{ duration: 0.6, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }}
    />
  );
}

function ToolBadge({ name }: { name: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#f9f8f6] border border-zinc-200 text-[12px] text-zinc-600 mb-2"
    >
      <motion.span
        className="w-1.5 h-1.5 rounded-full bg-[#d97757]"
        animate={{ opacity: [1, 0.3, 1] }}
        transition={{ duration: 1, repeat: Infinity }}
      />
      {name}…
    </motion.div>
  );
}



function EmptyState() {
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-center justify-center gap-3 select-none pointer-events-none"
    >
      <div className="w-12 h-12 rounded-2xl bg-[#d97757] flex items-center justify-center shadow-md shadow-[#d97757]/30">
        <span className="text-white text-[22px] font-bold tracking-tighter">m</span>
      </div>
      <div className="text-center">
        <h1 className="text-[28px] font-semibold text-zinc-800 tracking-tight leading-tight">
          {greeting}, Sourish
        </h1>
        <p className="text-[15px] text-zinc-400 mt-1">How can I help you today?</p>
      </div>
    </motion.div>
  );
}

const MSG_VARIANTS = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.2, ease: "easeOut" as const } },
};

export function MessageList({
  messages,
  streaming,
  streamingContent,
  streamingThinking,
  thinkingContent,
  thinkingDuration,
  activeToolName,
  isEmpty,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingContent]);

  return (
    /* Root IS the scroll container — flex-col so empty state can use flex-1 */
    <div className="flex-1 overflow-y-auto flex flex-col">
      {isEmpty ? (
        /* Empty state: fill remaining space and center */
        <div className="flex-1 flex items-center justify-center pb-24">
          <EmptyState />
        </div>
      ) : (
        /* Messages: normal block flow, no flex-1 needed */
        <div className="w-full max-w-3xl mx-auto px-6 pt-10 pb-6 flex flex-col gap-6">
          <AnimatePresence initial={false}>
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                variants={MSG_VARIANTS}
                initial="hidden"
                animate="visible"
                className={cn(
                  "flex flex-col w-full",
                  msg.role === "user" ? "items-end" : "items-start"
                )}
              >
                {msg.role === "user" ? (
                  /* User bubble */
                  <div
                    className={cn(
                      "max-w-[75%] px-4 py-3 rounded-2xl rounded-tr-md",
                      "bg-[#e9e9e7] text-zinc-800",
                      "text-[15px] leading-relaxed whitespace-pre-wrap"
                    )}
                  >
                    {msg.content}
                  </div>
                ) : (
                  <div className="w-full">
                    {msg.thinking && (
                      <ThinkingBlock thinking={msg.thinking} isStreaming={false} />
                    )}
                    <div className="prose-chat w-full max-w-full">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeHighlight]}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Active tool call indicator */}
          {activeToolName && (
            <motion.div
              variants={MSG_VARIANTS}
              initial="hidden"
              animate="visible"
              className="flex flex-col items-start w-full"
            >
              <ToolBadge name={activeToolName} />
            </motion.div>
          )}

          {/* Streaming response */}
          {streaming && (
            <motion.div
              variants={MSG_VARIANTS}
              initial="hidden"
              animate="visible"
              className="flex flex-col items-start w-full"
            >
              {/* Thinking block — shown while model reasons and after it finishes */}
              {streamingThinking ? (
                <ThinkingBlock thinking={thinkingContent} isStreaming={true} />
              ) : thinkingContent ? (
                <ThinkingBlock
                  thinking={thinkingContent}
                  isStreaming={false}
                  durationSeconds={thinkingDuration}
                />
              ) : null}

              {streamingContent ? (
                <div className="prose-chat w-full max-w-full">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {streamingContent}
                  </ReactMarkdown>
                  <StreamingCursor />
                </div>
              ) : !activeToolName && !streamingThinking && !thinkingContent ? (
                <ThinkingBlock thinking="" isStreaming={true} />
              ) : null}
            </motion.div>
          )}

          <div ref={bottomRef} className="h-1" />
        </div>
      )}
    </div>
  );
}
