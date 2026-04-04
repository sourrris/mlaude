export interface Session {
  id: string;
  title: string | null;
  updated_at: string;
}

export interface Message {
  id?: number;
  session_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string;
}

export interface RagChunk {
  source: string;
  source_type: "about" | "interest" | "behavior" | "general";
  score: number;
  preview: string;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  duration_ms: number;
  error: boolean;
}

export interface Trace {
  context_tokens: number;
  context_pct: number;
  context_limit: number;
  history_messages: number;
  memory_tokens: number;
  memory_writes: string[];
  rag: {
    query: string;
    count: number;
    duration_ms: number;
    chunks: RagChunk[];
  } | null;
  tool_calls: ToolCall[];
  first_token_ms: number;
  total_ms: number;
  response_tokens: number;
  warnings: string[];
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected";
