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
  } = useChat();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [traceOpen, setTraceOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  return (
    <div className="flex h-full w-full bg-zinc-950 overflow-hidden">

      {/* Sidebar */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 240, opacity: 1 }}
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

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0 bg-zinc-950">
        <TopBar
          title={activeSession?.title ?? null}
          status={status}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
          trace={trace}
          onOpenTrace={() => setTraceOpen(true)}
        />

        <MessageList
          messages={messages}
          streaming={streaming}
          streamingContent={streamingContent}
          activeToolName={activeToolName}
        />

        <ChatInput
          onSend={sendMessage}
          disabled={status !== "connected"}
          streaming={streaming}
        />
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
