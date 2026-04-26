"use client";

import { useEffect, useMemo, useRef, useState, startTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowUpRight, RefreshCcw } from "lucide-react";

import { ChatInputBar } from "@/components/chat/input-bar";
import { MessageList } from "@/components/chat/message-list";
import { RunsPanel } from "@/components/chat/runs-panel";
import { SourceSidebar } from "@/components/chat/source-sidebar";
import { WelcomeState } from "@/components/chat/welcome-state";
import { WorkspaceChrome } from "@/components/ui/workspace-chrome";
import { createSession, getModelSettings, getSessionDetail, streamChat, stopChat, uploadFile } from "@/lib/api";
import { applyPacketToMessage } from "@/lib/chat-state";
import type { AgentRun, AssistantPacket, ModelSettingsResponse, WorkspaceFile, WorkspaceMessage } from "@/lib/types";

function buildAssistantPlaceholder(requestId: string, sessionId: string): WorkspaceMessage {
  return {
    id: `assistant-${requestId}`,
    session_id: sessionId,
    parent_message_id: null,
    role: "assistant",
    content: "",
    model_name: null,
    packets: [],
    documents: [],
    citations: [],
    files: [],
    created_at: new Date().toISOString(),
    meta: { streaming: true, stop_reason: null },
  };
}

export function ChatWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeSessionId = searchParams.get("session");
  const activeView = searchParams.get("mode") === "runs" ? "runs" : "chat";

  const [messages, setMessages] = useState<WorkspaceMessage[]>([]);
  const [sessionTitle, setSessionTitle] = useState("New session");
  const [draftFiles, setDraftFiles] = useState<WorkspaceFile[]>([]);
  const [composerValue, setComposerValue] = useState("");
  const [sessionFiles, setSessionFiles] = useState<WorkspaceFile[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [liveRun, setLiveRun] = useState<AgentRun | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [selectedSourcesMessageId, setSelectedSourcesMessageId] = useState<string | null>(null);
  const [modelState, setModelState] = useState<ModelSettingsResponse | null>(null);
  const [selectedModel, setSelectedModel] = useState("");
  const [chatError, setChatError] = useState<string | null>(null);

  const currentRequestIdRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadModelState() {
      try {
        const response = await getModelSettings();
        if (!cancelled) {
          setModelState(response);
          setSelectedModel(
            response.models.includes(response.settings.default_chat_model)
              ? response.settings.default_chat_model
              : response.models[0] || response.settings.default_chat_model
          );
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
        }
      }
    }

    loadModelState();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadSession() {
      if (!activeSessionId) {
        setMessages([]);
        setDraftFiles([]);
        setSessionFiles([]);
        setRuns([]);
        setLiveRun(null);
        setSessionTitle("New session");
        setSelectedSourcesMessageId(null);
        setLoadingSession(false);
        return;
      }

      setLoadingSession(true);
      try {
        const detail = await getSessionDetail(activeSessionId);
        if (!cancelled) {
          setMessages(detail.messages);
          setSessionFiles(detail.files);
          setRuns(detail.runs);
          setLiveRun(null);
          setDraftFiles((current) =>
            current.filter((file) =>
              detail.files.some((sessionFile) => sessionFile.id === file.id)
            )
          );
          setSessionTitle(detail.session.title);
          setSelectedSourcesMessageId(null);
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
        }
      } finally {
        if (!cancelled) {
          setLoadingSession(false);
        }
      }
    }

    loadSession();
    return () => {
      cancelled = true;
    };
  }, [activeSessionId]);

  const selectedSourceMessage = useMemo(
    () =>
      messages.find(
        (message) =>
          message.id === selectedSourcesMessageId && message.role === "assistant"
      ) ?? null,
    [messages, selectedSourcesMessageId]
  );

  const selectedSourceUserFiles = useMemo(() => {
    if (!selectedSourceMessage?.parent_message_id) {
      return [];
    }
    return (
      messages.find((message) => message.id === selectedSourceMessage.parent_message_id)
        ?.files ?? []
    );
  }, [messages, selectedSourceMessage]);

  async function ensureSession(): Promise<string> {
    if (activeSessionId) {
      return activeSessionId;
    }

    const session = await createSession();
    window.dispatchEvent(new Event("mlaude:sessions-changed"));
    startTransition(() => {
      router.replace(`/?session=${session.id}${activeView === "runs" ? "&mode=runs" : ""}`);
    });
    return session.id;
  }

  async function refreshCurrentSession(sessionId: string) {
    const detail = await getSessionDetail(sessionId);
    setMessages(detail.messages);
    setSessionFiles(detail.files);
    setRuns(detail.runs);
    setSessionTitle(detail.session.title);
    window.dispatchEvent(new Event("mlaude:sessions-changed"));
  }

  function setViewMode(mode: "chat" | "runs") {
    const next = new URLSearchParams(searchParams.toString());
    if (mode === "runs") {
      next.set("mode", "runs");
    } else {
      next.delete("mode");
    }
    startTransition(() => {
      router.replace(`/?${next.toString()}`);
    });
  }

  async function handleSend(submittedValue?: string) {
    const nextValue = (submittedValue ?? composerValue).trim();
    if (!nextValue || streaming) {
      return;
    }

    setChatError(null);
    const sessionId = await ensureSession();
    const requestId = crypto.randomUUID();
    currentRequestIdRef.current = requestId;
    setStreaming(true);
    setLiveRun(null);

    const optimisticUser: WorkspaceMessage = {
      id: `user-${requestId}`,
      session_id: sessionId,
      parent_message_id: null,
      role: "user",
      content: nextValue,
      model_name: null,
      packets: [],
      documents: [],
      citations: [],
      files: draftFiles,
      created_at: new Date().toISOString(),
      meta: {},
    };
    const optimisticAssistant = buildAssistantPlaceholder(requestId, sessionId);

    setMessages((current) => [...current, optimisticUser, optimisticAssistant]);
    setComposerValue("");
    const attachments = [...draftFiles];
    setDraftFiles([]);

    try {
      await streamChat(
        {
          request_id: requestId,
          session_id: sessionId,
          content: nextValue,
          attachment_ids: attachments.map((file) => file.id),
          model: selectedModel || undefined,
          temperature: modelState?.settings.temperature,
        },
        (packet) => {
          if (packet.type === "run_start") {
            setLiveRun(packet.run);
          } else if (packet.type === "step_start" || packet.type === "step_result") {
            setLiveRun((current) => {
              if (!current || current.id !== packet.run_id) {
                return current;
              }
              const steps = current.steps.filter((step) => step.id !== packet.step.id);
              steps.push(packet.step);
              steps.sort((left, right) => left.order_index - right.order_index);
              return { ...current, steps };
            });
          } else if (packet.type === "run_complete") {
            setLiveRun(packet.run);
          } else if (packet.type === "run_error") {
            setChatError(packet.message);
          }

          setMessages((current) =>
            current.map((message) => {
              if (message.id !== optimisticAssistant.id) {
                return message;
              }

              const nextMessage = applyPacketToMessage(message, packet as AssistantPacket);
              if (packet.type === "stop") {
                return {
                  ...nextMessage,
                  meta: {
                    ...(nextMessage.meta ?? {}),
                    streaming: false,
                    stop_reason: packet.stop_reason ?? null,
                  },
                };
              }
              if (packet.type === "error") {
                setChatError(packet.message ?? "Chat stream failed.");
                return {
                  ...nextMessage,
                  meta: {
                    ...(nextMessage.meta ?? {}),
                    streaming: false,
                    stop_reason: "error",
                  },
                };
              }
              return nextMessage;
            })
          );
        }
      );
      await refreshCurrentSession(sessionId);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to stream the response.";
      setChatError(message);
    } finally {
      setStreaming(false);
      currentRequestIdRef.current = null;
      setLiveRun(null);
    }
  }

  async function handleStop() {
    if (!currentRequestIdRef.current) {
      return;
    }
    await stopChat(currentRequestIdRef.current);
  }

  async function handleUploadFiles(files: File[]) {
    const sessionId = await ensureSession();
    const uploaded = await Promise.all(
      files.map((file) =>
        uploadFile({
          file,
          scope: "chat",
          sessionId,
        })
      )
    );
    setDraftFiles((current) => [...current, ...uploaded]);
    setSessionFiles((current) => [...uploaded, ...current]);
    window.dispatchEvent(new Event("mlaude:sessions-changed"));
  }

  return (
    <WorkspaceChrome activeSection="chat" selectedSessionId={activeSessionId}>
      <div className="flex h-[calc(100vh-0px)] min-h-0 gap-4 px-4 pb-4 pt-2 lg:px-5 lg:pb-5">
        <div className="panel-surface flex min-w-0 flex-1 flex-col rounded-[2rem]">
          <div className="flex items-center justify-between border-b border-[color:var(--border-soft)] px-5 py-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-[color:var(--text-faint)]">
                Session
              </p>
              <h2 className="mt-1 text-lg font-semibold tracking-tight text-[color:var(--text-main)]">
                {sessionTitle}
              </h2>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center rounded-full border border-[color:var(--border-soft)] bg-[color:var(--bg-muted)] p-1">
                <button
                  type="button"
                  data-testid="session-view-chat"
                  onClick={() => setViewMode("chat")}
                  className={`rounded-full px-3 py-1.5 text-xs uppercase tracking-[0.16em] transition ${
                    activeView === "chat"
                      ? "bg-white text-[color:var(--text-main)] shadow-sm"
                      : "text-[color:var(--text-faint)]"
                  }`}
                >
                  Chat
                </button>
                <button
                  type="button"
                  data-testid="session-view-runs"
                  onClick={() => setViewMode("runs")}
                  className={`rounded-full px-3 py-1.5 text-xs uppercase tracking-[0.16em] transition ${
                    activeView === "runs"
                      ? "bg-white text-[color:var(--text-main)] shadow-sm"
                      : "text-[color:var(--text-faint)]"
                  }`}
                >
                  Runs
                </button>
              </div>
              <div className="rounded-full border border-[color:var(--border-soft)] bg-white px-3 py-2 text-xs uppercase tracking-[0.16em] text-[color:var(--text-faint)]">
                {modelState?.health.running
                  ? modelState.health.embedding_model_available
                    ? "Chat + Embeddings ready"
                    : "Embeddings missing"
                  : "Runtime offline"}
              </div>
              <button
                type="button"
                onClick={() => activeSessionId && refreshCurrentSession(activeSessionId)}
                className="flex items-center gap-2 rounded-full border border-[color:var(--border-soft)] bg-white px-3 py-2 text-sm text-[color:var(--text-soft)] transition hover:text-[color:var(--text-main)]"
              >
                <RefreshCcw size={14} />
                Refresh
              </button>
            </div>
          </div>

          {loadingSession ? (
            <div className="flex flex-1 items-center justify-center text-sm text-[color:var(--text-soft)]">
              Loading session…
            </div>
          ) : activeView === "runs" ? (
            <RunsPanel runs={runs} liveRun={liveRun} />
          ) : messages.length === 0 ? (
            <WelcomeState onSuggestion={(value) => void handleSend(value)} />
          ) : (
            <MessageList
              messages={messages}
              onOpenSources={(messageId) => setSelectedSourcesMessageId(messageId)}
            />
          )}

          <div className="border-t border-[color:var(--border-soft)] px-5 py-5">
            {chatError ? (
              <div className="mb-4 rounded-[1.25rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-[color:var(--warning)]">
                {chatError}
              </div>
            ) : null}

            {!modelState?.health.running ? (
              <div className="mb-4 flex items-center justify-between rounded-[1.25rem] border border-dashed border-[color:var(--border-soft)] bg-white/70 px-4 py-3 text-sm text-[color:var(--text-soft)]">
                <p>Local runtime is unavailable. Configure the local runtime or use test mode for development.</p>
                <button
                  type="button"
                  onClick={() => router.push("/settings")}
                  className="inline-flex items-center gap-2 text-[color:var(--accent)]"
                >
                  Open Settings
                  <ArrowUpRight size={14} />
                </button>
              </div>
            ) : null}

            <ChatInputBar
              value={composerValue}
              onChange={setComposerValue}
              onSubmit={() => void handleSend()}
              onStop={() => void handleStop()}
              draftFiles={draftFiles}
              onRemoveFile={(fileId) =>
                setDraftFiles((current) => current.filter((file) => file.id !== fileId))
              }
              onUploadFiles={(files) => void handleUploadFiles(files)}
              models={modelState?.models ?? []}
              selectedModel={selectedModel}
              onModelChange={setSelectedModel}
              disabled={!modelState}
              streaming={streaming}
            />
          </div>
        </div>

        {selectedSourcesMessageId ? (
          <div className="hidden w-[360px] shrink-0 xl:block">
            <SourceSidebar
              message={selectedSourceMessage}
              userFiles={selectedSourceUserFiles}
              onClose={() => setSelectedSourcesMessageId(null)}
            />
          </div>
        ) : null}
      </div>
    </WorkspaceChrome>
  );
}
