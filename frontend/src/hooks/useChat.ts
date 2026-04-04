import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectionStatus, Message, Session, Trace } from "@/types";

const WS_URL =
  import.meta.env.MODE === "development"
    ? `ws://localhost:7474/ws`
    : `ws://${window.location.host}/ws`;

const RECONNECT_DELAY_MS = 2000;

export function useChat() {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isUnmounting = useRef(false);
  const thinkingAccRef = useRef("");
  const thinkingStartRef = useRef<number | null>(null);

  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingThinking, setStreamingThinking] = useState(false);
  const [thinkingContent, setThinkingContent] = useState("");
  const [thinkingDuration, setThinkingDuration] = useState<number | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [activeToolName, setActiveToolName] = useState<string | null>(null);
  const [memoryContent, setMemoryContent] = useState<string | null>(null);

  const send = useCallback((payload: Record<string, unknown>) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    }
  }, []);

  const connect = useCallback(() => {
    if (ws.current && ws.current.readyState !== WebSocket.CLOSED) return;

    const socket = new WebSocket(WS_URL);
    ws.current = socket;
    setStatus("connecting");

    socket.onopen = () => {
      setStatus("connected");
      send({ type: "list_sessions" });
    };

    socket.onclose = () => {
      setStatus("disconnected");
      if (!isUnmounting.current) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    socket.onerror = () => {
      socket.close();
    };

    socket.onmessage = (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (msg.type) {
        case "sessions":
          setSessions((msg.data as Session[]) ?? []);
          break;

        case "session_created":
          setActiveSessionId(msg.session_id as string);
          setTrace(null);
          send({ type: "list_sessions" });
          break;

        case "history":
          setMessages((msg.messages as Message[]) ?? []);
          setTrace(null);
          break;

        case "thinking_start":
          setStreaming(true);
          setStreamingThinking(true);
          thinkingAccRef.current = "";
          setThinkingContent("");
          thinkingStartRef.current = Date.now();
          break;

        case "thinking_token":
          thinkingAccRef.current += (msg.content as string);
          setThinkingContent(thinkingAccRef.current);
          break;

        case "thinking_done":
          setStreamingThinking(false);
          if (thinkingStartRef.current !== null) {
            setThinkingDuration(Math.round((Date.now() - thinkingStartRef.current) / 1000));
            thinkingStartRef.current = null;
          }
          break;

        case "token":
          setStreaming(true);
          setStreamingContent((prev) => prev + (msg.content as string));
          break;

        case "done":
          setStreaming(false);
          setStreamingContent((prev) => {
            if (prev) {
              const thinking = thinkingAccRef.current || undefined;
              setMessages((msgs) => [
                ...msgs,
                { role: "assistant", content: prev, thinking },
              ]);
            }
            return "";
          });
          thinkingAccRef.current = "";
          setThinkingContent("");
          setThinkingDuration(null);
          setStreamingThinking(false);
          setActiveToolName(null);
          break;

        case "tool_start":
          setActiveToolName(msg.tool as string);
          break;

        case "tool_done":
          setActiveToolName(null);
          break;

        case "trace":
          setTrace(msg.data as Trace);
          break;

        case "title_updated":
          setSessions((prev) =>
            prev.map((s) =>
              s.id === (msg.session_id as string)
                ? { ...s, title: msg.title as string }
                : s
            )
          );
          break;

        case "session_deleted":
          setSessions((prev) =>
            prev.filter((s) => s.id !== (msg.session_id as string))
          );
          if (activeSessionId === (msg.session_id as string)) {
            setActiveSessionId(null);
            setMessages([]);
            setTrace(null);
          }
          break;

        case "memory":
          setMemoryContent(msg.content as string);
          break;

        case "memory_saved":
          // no-op — modal can close after this
          break;

        case "reindex_done":
          // Could surface this in UI — for now just ignore
          break;

        case "error":
          console.error("[ws] server error:", msg.content);
          break;
      }
    };
  }, [send, activeSessionId]);

  // Initial connect
  useEffect(() => {
    isUnmounting.current = false;
    connect();
    return () => {
      isUnmounting.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const newSession = useCallback(() => {
    setMessages([]);
    setActiveSessionId(null);
    setStreaming(false);
    setStreamingContent("");
    setStreamingThinking(false);
    thinkingAccRef.current = "";
    setThinkingContent("");
    setThinkingDuration(null);
    setTrace(null);
    setActiveToolName(null);
    send({ type: "new_session" });
  }, [send]);

  const loadSession = useCallback(
    (id: string) => {
      setActiveSessionId(id);
      setStreaming(false);
      setStreamingContent("");
      setStreamingThinking(false);
      thinkingAccRef.current = "";
      setThinkingContent("");
      setThinkingDuration(null);
      setActiveToolName(null);
      send({ type: "load_session", session_id: id });
    },
    [send]
  );

  const deleteSession = useCallback(
    (id: string) => {
      send({ type: "delete_session", session_id: id });
    },
    [send]
  );

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim() || streaming) return;
      const sid = activeSessionId ?? "";
      setMessages((prev) => [...prev, { role: "user", content }]);
      setTrace(null);
      send({ type: "message", session_id: sid, content });
    },
    [send, activeSessionId, streaming]
  );

  const reindex = useCallback(() => {
    send({ type: "reindex" });
  }, [send]);

  const loadMemory = useCallback(() => {
    send({ type: "get_memory" });
  }, [send]);

  const saveMemory = useCallback((content: string) => {
    send({ type: "update_memory_raw", content });
  }, [send]);

  return {
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
  };
}
