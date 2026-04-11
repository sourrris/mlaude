import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChromaDbInfo,
  DiagStats,
  DiagTrace,
  SystemInfo,
  TracesResponse,
} from "../types";

const WS_URL =
  import.meta.env.MODE === "development"
    ? "ws://localhost:7474/ws"
    : `ws://${window.location.host}/ws`;

const POLL_INTERVAL = 10_000;

export function useDiagnostics() {
  const ws = useRef<WebSocket | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const [connected, setConnected] = useState(false);
  const [traces, setTraces] = useState<DiagTrace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<DiagTrace | null>(null);
  const [activeDate, setActiveDate] = useState("");
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [chromaDb, setChromaDb] = useState<ChromaDbInfo | null>(null);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [stats, setStats] = useState<DiagStats | null>(null);

  const send = useCallback((payload: Record<string, unknown>) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    }
  }, []);

  const requestTraces = useCallback(
    (date?: string) => {
      send({ type: "get_traces", date: date ?? activeDate, limit: 200 });
    },
    [send, activeDate]
  );

  const requestAll = useCallback(() => {
    requestTraces();
    send({ type: "get_chromadb_stats" });
    send({ type: "get_system_info" });
    send({ type: "get_diag_stats", days: 1 });
  }, [requestTraces, send]);

  const changeDate = useCallback(
    (date: string) => {
      setActiveDate(date);
      setSelectedTrace(null);
      send({ type: "get_traces", date, limit: 200 });
      send({ type: "get_diag_stats", days: 1 });
    },
    [send]
  );

  // Connect
  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    ws.current = socket;

    socket.onopen = () => {
      setConnected(true);
      // Request everything on connect
      socket.send(JSON.stringify({ type: "get_traces", limit: 200 }));
      socket.send(JSON.stringify({ type: "get_chromadb_stats" }));
      socket.send(JSON.stringify({ type: "get_system_info" }));
      socket.send(JSON.stringify({ type: "get_diag_stats", days: 1 }));
    };

    socket.onclose = () => setConnected(false);
    socket.onerror = () => socket.close();

    socket.onmessage = (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (msg.type) {
        case "traces": {
          const data = msg as unknown as TracesResponse;
          setTraces(data.traces);
          setAvailableDates(data.dates_available);
          if (data.date) setActiveDate(data.date);
          break;
        }
        case "chromadb_stats":
          setChromaDb(msg as unknown as ChromaDbInfo);
          break;
        case "system_info":
          setSystemInfo(msg as unknown as SystemInfo);
          break;
        case "diag_stats":
          setStats(msg as unknown as DiagStats);
          break;
        case "trace":
          // Live trace from chat activity — prepend
          setTraces((prev) => [msg.data as DiagTrace, ...prev]);
          break;
      }
    };

    return () => {
      socket.close();
    };
  }, []);

  // Poll for new traces (pause when tab hidden)
  useEffect(() => {
    const poll = () => {
      if (document.visibilityState === "visible") {
        requestTraces();
      }
    };
    pollTimer.current = setInterval(poll, POLL_INTERVAL);
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [requestTraces]);

  return {
    connected,
    traces,
    selectedTrace,
    setSelectedTrace,
    activeDate,
    availableDates,
    changeDate,
    chromaDb,
    systemInfo,
    stats,
    requestAll,
  };
}
