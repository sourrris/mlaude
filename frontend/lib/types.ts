export type PacketType =
  | "message_start"
  | "message_delta"
  | "message_end"
  | "stop"
  | "error"
  | "run_start"
  | "step_start"
  | "step_result"
  | "run_complete"
  | "run_error"
  | "reasoning_start"
  | "reasoning_delta"
  | "reasoning_done"
  | "search_tool_start"
  | "search_tool_queries_delta"
  | "search_tool_documents_delta"
  | "file_reader_start"
  | "file_reader_result"
  | "python_tool_start"
  | "python_tool_delta"
  | "open_url_start"
  | "open_url_urls"
  | "open_url_documents"
  | "citation_info"
  | "section_end";

export interface WorkspaceSession {
  id: string;
  title: string;
  last_message_preview: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface WorkspaceFile {
  id: string;
  session_id: string | null;
  scope: "chat" | "library";
  filename: string;
  title: string;
  content_type: string | null;
  byte_size: number;
  chunk_count: number;
  created_at: string | null;
}

export interface SourceDocument {
  document_id: string;
  file_id: string | null;
  title: string;
  source: string;
  source_kind?: "web_result" | "web_page" | "file_excerpt" | "python_output";
  section?: string | null;
  content: string;
  preview: string;
  score: number;
  query?: string | null;
  retrieval_score?: number;
  fetched_at?: string | null;
  extract_status?: string | null;
}

export interface CitationPacket {
  type: "citation_info";
  citation_number: number;
  document_id: string;
}

export interface RunStep {
  id: string;
  run_id: string;
  step_type: string;
  order_index: number;
  status: "pending" | "running" | "completed" | "skipped" | "error";
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_text?: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentRun {
  id: string;
  request_id: string;
  session_id: string;
  user_message_id: string | null;
  assistant_message_id: string | null;
  status: "pending" | "running" | "completed" | "stopped" | "error";
  stop_reason?: string | null;
  plan: string[];
  timings: Record<string, unknown>;
  artifacts: Record<string, unknown>;
  meta: Record<string, unknown>;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  steps: RunStep[];
}

export type AssistantPacket =
  | {
      type: "message_start";
      id: string;
      content: string;
      final_documents?: SourceDocument[];
    }
  | {
      type: "run_start";
      run: AgentRun;
    }
  | {
      type: "step_start";
      run_id: string;
      step: RunStep;
    }
  | {
      type: "step_result";
      run_id: string;
      step: RunStep;
    }
  | {
      type: "run_complete";
      run: AgentRun;
    }
  | {
      type: "run_error";
      run_id: string;
      message: string;
    }
  | {
      type: "message_delta";
      content: string;
    }
  | {
      type: "message_end";
    }
  | {
      type: "stop";
      stop_reason?: string;
    }
  | {
      type: "error";
      message?: string;
    }
  | {
      type: "reasoning_start";
    }
  | {
      type: "reasoning_delta";
      reasoning: string;
    }
  | {
      type: "reasoning_done";
    }
  | {
      type: "search_tool_start";
      is_internet_search?: boolean;
    }
  | {
      type: "search_tool_queries_delta";
      queries: string[];
    }
  | {
      type: "search_tool_documents_delta";
      documents: SourceDocument[];
    }
  | {
      type: "file_reader_start";
    }
  | {
      type: "file_reader_result";
      file_id: string;
      file_name: string;
      start_char: number;
      end_char: number;
      content: string;
      preview: string;
    }
  | {
      type: "python_tool_start";
      code: string;
    }
  | {
      type: "python_tool_delta";
      stdout: string;
      stderr: string;
      file_ids: string[];
    }
  | {
      type: "open_url_start";
    }
  | {
      type: "open_url_urls";
      urls: string[];
    }
  | {
      type: "open_url_documents";
      documents: SourceDocument[];
    }
  | CitationPacket
  | {
      type: "section_end";
    };

export interface WorkspaceMessage {
  id: string;
  session_id: string;
  parent_message_id: string | null;
  role: "user" | "assistant";
  content: string;
  model_name: string | null;
  packets: AssistantPacket[];
  documents: SourceDocument[];
  citations: CitationPacket[];
  files: WorkspaceFile[];
  created_at: string | null;
  meta?: Record<string, unknown>;
}

export interface SessionDetailResponse {
  session: WorkspaceSession;
  messages: WorkspaceMessage[];
  files: WorkspaceFile[];
  runs: AgentRun[];
}

export interface RuntimeHealth {
  running: boolean;
  models: string[];
  model_available: boolean;
  embedding_model_available?: boolean;
  default_embedding_model?: string;
  error?: string;
}

export interface ModelSettings {
  ollama_base_url: string;
  default_chat_model: string;
  default_embedding_model: string;
  temperature: number;
}

export interface ModelSettingsResponse {
  settings: ModelSettings;
  models: string[];
  health: RuntimeHealth;
}

export interface ChatStreamRequest {
  request_id: string;
  session_id: string;
  content: string;
  attachment_ids: string[];
  model?: string;
  temperature?: number;
}
