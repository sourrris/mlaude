import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useChat } from "@/hooks/useChat";
import { SessionSidebar } from "@/components/sidebar/SessionSidebar";
import { TopBar } from "@/components/chat/TopBar";
import { MessageList } from "@/components/chat/MessageList";
import { ChatInput } from "@/components/chat/ChatInput";
import { TraceDrawer } from "@/components/trace/TraceDrawer";
import { MemoryEditor } from "@/components/memory/MemoryEditor";

export default function App() {
  const {
    status,
    sessions,
    activeSessionId,
    messages,
    streaming,
    streamingContent,
    streamingThinking,
    thinkingContent,
    thinkingDuration,
    trace,
    activeToolName,
    newSession,
    loadSession,
    deleteSession,
    sendMessage,
    reindex,
    memoryContent,
    loadMemory,
    saveMemory,
    models,
    currentModel,
    setCurrentModel,
  } = useChat();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [traceOpen, setTraceOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;
  const isEmpty = messages.length === 0 && !streaming;

  return (
    <div className="flex h-full w-full bg-[#f9f8f6] overflow-hidden text-zinc-800 font-sans">
      {/* Sidebar */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden shrink-0"
          >
            <SessionSidebar
              sessions={sessions}
              activeSessionId={activeSessionId}
              onNew={newSession}
              onLoad={loadSession}
              onDelete={deleteSession}
              onReindex={reindex}
              onOpenMemory={() => setMemoryOpen(true)}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main chat area — stable single layout, no conditional branch */}
      <main className="flex-1 flex flex-col min-w-0 bg-white relative rounded-tl-2xl shadow-sm border-t border-l border-black/5 z-10">
       <TopBar
         title={activeSession?.title ?? null}
         status={status}
         sidebarOpen={sidebarOpen}
         onToggleSidebar={() => setSidebarOpen((v) => !v)}
         trace={trace}
         onOpenTrace={() => setTraceOpen(true)}
         models={models}
         currentModel={currentModel}
         onModelChange={(model: string) => {
           setCurrentModel(model);
         }}
       />

        {/* Message area + input — stable flex column */}
        <div className="flex-1 flex flex-col min-h-0">
          <MessageList
            messages={messages}
            streaming={streaming}
            streamingContent={streamingContent}
            streamingThinking={streamingThinking}
            thinkingContent={thinkingContent}
            thinkingDuration={thinkingDuration}
            activeToolName={activeToolName}
            isEmpty={isEmpty}
          />

          {/* Input — pinned at bottom, no hard border */}
          <div className="relative shrink-0 bg-white">
            {/* Gradient fade so messages don't hard-cut into input */}
            <div className="pointer-events-none absolute -top-12 inset-x-0 h-12 bg-gradient-to-t from-white to-transparent" />
            <ChatInput
              onSend={sendMessage}
              disabled={status !== "connected"}
              streaming={streaming}
            />
          </div>
        </div>
      </main>

      {/* Trace panel */}
      <TraceDrawer
        trace={trace}
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
      />

      {/* Memory editor */}
      <MemoryEditor
        open={memoryOpen}
        content={memoryContent}
        onClose={() => setMemoryOpen(false)}
        onLoad={loadMemory}
        onSave={saveMemory}
      />
    </div>
  );
}
