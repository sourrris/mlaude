/* Diagnostics-specific types — mirrors backend observer.py trace payload. */

export interface DiagRagChunk {
  source: string;
  source_type: "about" | "interest" | "behavior" | "general";
  score: number;
  preview: string;
}

export interface DiagToolCall {
  name: string;
  args: Record<string, unknown>;
  result_preview?: string;
  duration_ms: number;
  error: boolean;
}

export interface DiagRag {
  query: string;
  count: number;
  duration_ms: number;
  rag_tokens?: number;
  chunks: DiagRagChunk[];
  /* Fields from JSONL log (not WS) */
  sources?: string[];
  scores?: number[];
}

export interface DiagTrace {
  ts?: string;
  request_id?: string;
  session_id?: string;
  system_prompt_tokens?: number;
  context_tokens: number;
  context_pct: number;
  context_limit?: number;
  history_messages: number;
  memory_tokens: number;
  memory_writes: string[];
  rag: DiagRag | null;
  tool_calls: DiagToolCall[];
  first_token_ms: number;
  total_ms: number;
  response_tokens: number;
  warnings: string[];
}

export interface TracesResponse {
  type: "traces";
  date: string;
  dates_available: string[];
  traces: DiagTrace[];
  total: number;
}

export interface ChromaDbInfo {
  type: "chromadb_stats";
  collection_name: string;
  chunk_count: number;
  knowledge_files: { path: string; source_type: string }[];
  knowledge_dir: string;
  chromadb_dir: string;
}

export interface SystemInfo {
  type: "system_info";
  model: string;
  embedding_model: string;
  context_limit: number;
  ollama_url: string;
  memory_path: string;
  memory_size_bytes: number;
  memory_tokens_approx: number;
  knowledge_dir: string;
  knowledge_file_count: number;
  mlaude_home: string;
}

export interface DiagStats {
  type: "diag_stats";
  request_count: number;
  avg_total_ms?: number;
  avg_first_token_ms?: number;
  avg_context_pct?: number;
  tool_call_counts?: Record<string, number>;
  warning_count?: number;
  rag_avg_duration_ms?: number;
  rag_avg_chunks?: number;
  latency_buckets?: Record<string, number>;
}
