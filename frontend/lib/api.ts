import type {
  AssistantPacket,
  ChatStreamRequest,
  ModelSettings,
  ModelSettingsResponse,
  SessionDetailResponse,
  WorkspaceFile,
  WorkspaceSession,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:7474";

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function listSessions(query = ""): Promise<WorkspaceSession[]> {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return requestJson<WorkspaceSession[]>(`/api/sessions${suffix}`);
}

export async function createSession(): Promise<WorkspaceSession> {
  return requestJson<WorkspaceSession>("/api/sessions", { method: "POST" });
}

export async function getSessionDetail(
  sessionId: string
): Promise<SessionDetailResponse> {
  return requestJson<SessionDetailResponse>(`/api/sessions/${sessionId}`);
}

export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export async function listFiles(
  params: Record<string, string | undefined>
): Promise<WorkspaceFile[]> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) {
      search.set(key, value);
    }
  }
  const suffix = search.size ? `?${search.toString()}` : "";
  return requestJson<WorkspaceFile[]>(`/api/files${suffix}`);
}

export async function uploadFile(input: {
  file: File;
  scope: "chat" | "library";
  sessionId?: string;
}): Promise<WorkspaceFile> {
  const formData = new FormData();
  formData.set("file", input.file);
  formData.set("scope", input.scope);
  if (input.sessionId) {
    formData.set("session_id", input.sessionId);
  }

  const response = await fetch(apiUrl("/api/files/upload"), {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Upload failed: ${response.status}`);
  }
  return (await response.json()) as WorkspaceFile;
}

export async function getModelSettings(): Promise<ModelSettingsResponse> {
  return requestJson<ModelSettingsResponse>("/api/settings/model");
}

export async function discoverModels(baseUrl?: string): Promise<string[]> {
  const suffix = baseUrl
    ? `?base_url=${encodeURIComponent(baseUrl)}`
    : "";
  const response = await requestJson<{ models: string[] }>(
    `/api/settings/model/discover${suffix}`
  );
  return response.models;
}

export async function updateModelSettings(
  payload: ModelSettings
): Promise<ModelSettingsResponse> {
  return requestJson<ModelSettingsResponse>("/api/settings/model", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function stopChat(requestId: string): Promise<void> {
  await requestJson(`/api/chat/stop/${requestId}`, { method: "POST" });
}

export async function streamChat(
  payload: ChatStreamRequest,
  onPacket: (packet: AssistantPacket) => void
): Promise<void> {
  const response = await fetch(apiUrl("/api/chat/stream"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const body = await response.text();
    throw new Error(body || "Failed to start chat stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }
      onPacket(JSON.parse(line) as AssistantPacket);
    }
  }

  if (buffer.trim()) {
    onPacket(JSON.parse(buffer) as AssistantPacket);
  }
}
