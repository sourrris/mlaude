export type PacketType =
  | "message_start"
  | "message_delta"
  | "message_end"
  | "stop"
  | "error"
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
  section?: string | null;
  content: string;
  preview: string;
  score: number;
}

export interface CitationPacket {
  type: "citation_info";
  citation_number: number;
  document_id: string;
}

export type AssistantPacket =
  | {
      type: "message_start";
      id: string;
      content: string;
      final_documents?: SourceDocument[];
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
}

export interface RuntimeHealth {
  running: boolean;
  models: string[];
  model_available: boolean;
  error?: string;
}

export interface ModelSettings {
  ollama_base_url: string;
  default_chat_model: string;
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
