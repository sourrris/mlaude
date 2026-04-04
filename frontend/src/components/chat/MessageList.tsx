import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";
import type { Message } from "@/types";

interface Props {
  messages: Message[];
  streaming: boolean;
  streamingContent: string;
  activeToolName: string | null;
}

function StreamingCursor() {
  return (
    <motion.span
      className="inline-block w-[2px] h-[15px] ml-0.5 rounded-full bg-amber-400 align-text-bottom"
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
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-900 border border-zinc-800 text-[12px] text-zinc-400"
    >
      <motion.span
        className="w-1.5 h-1.5 rounded-full bg-amber-400"
        animate={{ opacity: [1, 0.3, 1] }}
        transition={{ duration: 1, repeat: Infinity }}
      />
      {name}…
    </motion.div>
  );
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 0.2, 0.4].map((delay, i) => (
        <motion.span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-zinc-600"
          animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }}
          transition={{ duration: 1.2, repeat: Infinity, delay, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

function AssistantLabel() {
  return (
    <div className="flex items-center gap-1.5 mb-2">
      <div className="w-5 h-5 rounded-md bg-amber-400 flex items-center justify-center shrink-0">
        <span className="text-black text-[9px] font-bold">m</span>
      </div>
      <span className="text-[11px] font-semibold text-amber-400 tracking-wide uppercase">
        mlaude
      </span>
    </div>
  );
}

function UserLabel() {
  return (
    <div className="flex justify-end mb-2">
      <span className="text-[11px] font-semibold text-zinc-500 tracking-wide uppercase">
        you
      </span>
    </div>
  );
}

const MSG_VARIANTS = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.22, ease: "easeOut" as const } },
};

export function MessageList({ messages, streaming, streamingContent, activeToolName }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingContent]);

  if (messages.length === 0 && !streaming) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 px-8 select-none">
        <div className="w-12 h-12 rounded-2xl bg-amber-400/10 border border-amber-400/20 flex items-center justify-center">
          <span className="text-amber-400 text-xl font-bold">m</span>
        </div>
        <div className="text-center">
          <p className="text-zinc-300 font-medium text-[15px] mb-1">What are you thinking about?</p>
          <p className="text-zinc-600 text-[13px]">Physics, history, philosophy — anywhere.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl w-full mx-auto px-5 py-8 flex flex-col gap-7">
        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              variants={MSG_VARIANTS}
              initial="hidden"
              animate="visible"
              className={cn("flex flex-col", msg.role === "user" ? "items-end" : "items-start")}
            >
              {msg.role === "user" ? <UserLabel /> : <AssistantLabel />}

              {msg.role === "user" ? (
                <div className="max-w-[82%] bg-zinc-800/80 border border-zinc-700/60 rounded-2xl rounded-tr-md px-4 py-3 text-[14px] text-zinc-100 leading-relaxed whitespace-pre-wrap">
                  {msg.content}
                </div>
              ) : (
                <div className="prose-chat w-full">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Active tool call */}
        {activeToolName && (
          <motion.div variants={MSG_VARIANTS} initial="hidden" animate="visible" className="flex flex-col items-start">
            <AssistantLabel />
            <ToolBadge name={activeToolName} />
          </motion.div>
        )}

        {/* Streaming */}
        {streaming && (
          <motion.div variants={MSG_VARIANTS} initial="hidden" animate="visible" className="flex flex-col items-start">
            <AssistantLabel />
            {streamingContent ? (
              <div className="prose-chat w-full">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                  {streamingContent}
                </ReactMarkdown>
                <StreamingCursor />
              </div>
            ) : !activeToolName ? (
              <ThinkingDots />
            ) : null}
          </motion.div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
