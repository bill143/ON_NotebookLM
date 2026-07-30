/**
 * Nexus API Client — Typed HTTP client for the backend
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

// ── Types ────────────────────────────────────────────────────

export interface Notebook {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  tags: string[];
  pinned: boolean;
  source_count: number;
  created_at: string;
  updated_at: string;
}

export interface Source {
  id: string;
  title: string;
  source_type: string;
  status: string;
  word_count: number;
  topics: string[];
  created_at: string;
}

export interface Artifact {
  id: string;
  title: string;
  artifact_type: string;
  status: string;
  content?: string;
  storage_url?: string;
  duration_seconds?: number;
  created_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  turn_number?: number;
  model_used?: string;
  citations?: Array<{ source_id: string; source_title: string; cited_text: string }>;
}

export interface ChatSession {
  id: string;
  title: string;
  notebook_id?: string;
  message_count: number;
  created_at: string;
}

export interface AIModel {
  id: string;
  name: string;
  provider: string;
  model_type: string;
  model_id_string: string;
  is_local: boolean;
  is_active: boolean;
  cost_per_1k_input: number;
  cost_per_1k_output: number;
}

export interface UsageSummary {
  total_tokens: number;
  total_cost_usd: number;
  by_provider: Record<string, { tokens: number; cost_usd: number }>;
  by_feature: Record<string, { tokens: number; cost_usd: number }>;
}

export interface BudgetStatus {
  allowed: boolean;
  usage_usd: number;
  limit_usd: number;
  remaining_usd: number;
  utilization_pct: number;
}

export interface ResearchResult {
  session_id: string;
  turn_id: string;
  turn_number: number;
  answer: string;
  citations: Array<{ source_id: string; source_title: string; cited_text: string; relevance: number }>;
  follow_up_questions: string[];
  model_used: string;
  latency_ms: number;
  total_turns: number;
}

export interface ResearchSession {
  id: string;
  title: string;
  notebook_id?: string;
  turn_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface ExportFormat {
  id: string;
  name: string;
  mime: string;
  icon: string;
}

export interface FlashCard {
  id: string;
  front: string;
  back: string;
  tags: string[];
  difficulty: number;
  stability: number;
  due_at: string;
  review_count: number;
  state: number;
}

export interface AppSettings {
  theme: string;
  default_model: string;
  budget_limit_usd: number;
  api_keys: Record<string, string>;
}

export interface PodcastPresetCatalog {
  default: {
    format: string;
    length: string;
    language: string;
    speaker_profile: string;
    speech_rate: number;
  };
  formats: string[];
  lengths: string[];
  speaker_profiles: string[];
  languages_hint: string[];
  speech_rate_range: { min: number; max: number };
}

// ── API Client ───────────────────────────────────────────────

class NexusClient {
  private token: string = "";

  setToken(token: string) {
    this.token = token;
  }

  private headers(): HeadersInit {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.token) {
      h["Authorization"] = `Bearer ${this.token}`;
    }
    return h;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: this.headers(),
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        error: { message: response.statusText },
      }));
      throw new Error(error.error?.message || `API Error: ${response.status}`);
    }

    if (response.status === 204) return undefined as T;
    return response.json();
  }

  // ── Notebooks ────────────────────────────────────
  async listNotebooks(): Promise<Notebook[]> {
    return this.request("GET", "/api/v1/notebooks");
  }

  async createNotebook(data: Partial<Notebook>): Promise<Notebook> {
    return this.request("POST", "/api/v1/notebooks", data);
  }

  async getNotebook(id: string): Promise<Notebook & { sources: Source[] }> {
    return this.request("GET", `/api/v1/notebooks/${id}`);
  }

  async updateNotebook(id: string, data: Partial<Notebook>): Promise<Notebook> {
    return this.request("PATCH", `/api/v1/notebooks/${id}`, data);
  }

  async deleteNotebook(id: string): Promise<void> {
    return this.request("DELETE", `/api/v1/notebooks/${id}`);
  }

  // ── Sources ──────────────────────────────────────
  async listSources(notebookId?: string): Promise<Source[]> {
    const qs = notebookId ? `?notebook_id=${notebookId}` : "";
    return this.request("GET", `/api/v1/sources${qs}`);
  }

  async createTextSource(data: {
    content: string;
    title: string;
    notebook_id?: string;
  }): Promise<Source> {
    return this.request("POST", "/api/v1/sources/from-text", data);
  }

  async createUrlSource(data: {
    url: string;
    title: string;
    notebook_id?: string;
  }): Promise<Source> {
    return this.request("POST", "/api/v1/sources/from-url", data);
  }

  async searchSources(
    query: string,
    searchType: "text" | "vector" | "hybrid" = "hybrid",
    limit: number = 10,
    options?: {
      searchProfile?: "fast" | "balanced" | "deep";
      fusionK?: number;
      minScore?: number;
    }
  ): Promise<Source[]> {
    return this.request("POST", "/api/v1/sources/search", {
      query,
      search_type: searchType,
      limit,
      search_profile: options?.searchProfile ?? "balanced",
      fusion_k: options?.fusionK ?? 60,
      min_score: options?.minScore ?? 0.5,
    });
  }

  async deleteSource(id: string): Promise<void> {
    return this.request("DELETE", `/api/v1/sources/${id}`);
  }

  // ── Artifacts ────────────────────────────────────
  async listArtifacts(notebookId?: string): Promise<Artifact[]> {
    const qs = notebookId ? `?notebook_id=${notebookId}` : "";
    return this.request("GET", `/api/v1/artifacts${qs}`);
  }

  async createArtifact(data: {
    notebook_id: string;
    title: string;
    artifact_type: string;
    generation_config?: Record<string, unknown>;
  }): Promise<Artifact> {
    return this.request("POST", "/api/v1/artifacts", data);
  }

  async getArtifact(id: string): Promise<Artifact> {
    return this.request("GET", `/api/v1/artifacts/${id}`);
  }

  async cancelArtifact(id: string): Promise<Artifact> {
    return this.request("POST", `/api/v1/artifacts/${id}/cancel`);
  }

  async getPodcastPresets(): Promise<PodcastPresetCatalog> {
    return this.request("GET", "/api/v1/artifacts/podcast/presets");
  }

  // ── Chat ─────────────────────────────────────────
  async sendMessage(data: {
    content: string;
    session_id?: string;
    notebook_id?: string;
    stream?: boolean;
  }): Promise<{
    content: string;
    session_id: string;
    turn_number: number;
    citations: ChatMessage["citations"];
  }> {
    return this.request("POST", "/api/v1/chat", data);
  }

  async listSessions(notebookId?: string): Promise<ChatSession[]> {
    const qs = notebookId ? `?notebook_id=${notebookId}` : "";
    return this.request("GET", `/api/v1/chat/sessions${qs}`);
  }

  async getSessionMessages(sessionId: string): Promise<ChatMessage[]> {
    return this.request("GET", `/api/v1/chat/sessions/${sessionId}/messages`);
  }

  // ── Models ───────────────────────────────────────
  async listModels(): Promise<AIModel[]> {
    return this.request("GET", "/api/v1/models");
  }

  async getUsageSummary(days?: number): Promise<UsageSummary> {
    const qs = days ? `?days=${days}` : "";
    return this.request("GET", `/api/v1/models/usage/summary${qs}`);
  }

  async getBudgetStatus(): Promise<BudgetStatus> {
    return this.request("GET", "/api/v1/models/usage/budget");
  }

  // ── Research ─────────────────────────────────────
  async researchQuery(data: {
    query: string;
    session_id?: string;
    notebook_id?: string;
    profile?: "auto" | "quick" | "standard" | "deep";
    max_follow_ups?: number;
  }): Promise<ResearchResult> {
    return this.request("POST", "/api/v1/research", data);
  }

  async listResearchSessions(notebookId?: string): Promise<ResearchSession[]> {
    const qs = notebookId ? `?notebook_id=${notebookId}` : "";
    return this.request("GET", `/api/v1/research/sessions${qs}`);
  }

  async getResearchSession(sessionId: string): Promise<Record<string, unknown>> {
    return this.request("GET", `/api/v1/research/sessions/${sessionId}`);
  }

  // ── Export ───────────────────────────────────────
  async exportContent(data: {
    artifact_id?: string;
    notebook_id?: string;
    title?: string;
    content?: string;
    format: string;
  }): Promise<Blob> {
    const response = await fetch(`${API_BASE}/api/v1/export`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error(`Export failed: ${response.status}`);
    return response.blob();
  }

  async listExportFormats(): Promise<{ formats: ExportFormat[] }> {
    return this.request("GET", "/api/v1/export/formats");
  }

  // ── File Upload ─────────────────────────────────
  async uploadSource(file: File, notebookId?: string): Promise<Source> {
    const formData = new FormData();
    formData.append("file", file);
    if (notebookId) formData.append("notebook_id", notebookId);

    const h: Record<string, string> = {};
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;

    const response = await fetch(`${API_BASE}/api/v1/sources/upload`, {
      method: "POST",
      headers: h,
      body: formData,
    });
    if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
    return response.json();
  }

  // ── Flashcards ──────────────────────────────────
  async getDueFlashcards(notebookId?: string, limit = 20): Promise<FlashCard[]> {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (notebookId) qs.set("notebook_id", notebookId);
    return this.request("GET", `/api/v1/brain/flashcards/due?${qs}`);
  }

  async reviewFlashcard(id: string, rating: number): Promise<{ next_due: string; difficulty: number; stability: number }> {
    return this.request("POST", `/api/v1/brain/flashcards/${id}/review`, { rating });
  }

  // ── Health ───────────────────────────────────────
  async healthCheck(): Promise<{ status: string; checks: Record<string, string> }> {
    return this.request("GET", "/health/ready");
  }

  // ── WebSocket ────────────────────────────────────
  createChatSocket(
    sessionId?: string,
    onMessage?: (data: unknown) => void,
    onOpen?: () => void,
  ): ReconnectingSocket {
    const params = new URLSearchParams({
      token: this.token,
      ...(sessionId ? { session_id: sessionId } : {}),
    });
    return createReconnectingWebSocket(
      `${WS_BASE}/api/v1/ws/chat?${params}`,
      onMessage ?? (() => {}),
      onOpen,
    );
  }

  createCollabSocket(
    notebookId: string,
    onMessage?: (data: unknown) => void,
    onOpen?: () => void,
  ): ReconnectingSocket {
    const params = new URLSearchParams({
      token: this.token,
      notebook_id: notebookId,
    });
    return createReconnectingWebSocket(
      `${WS_BASE}/api/v1/ws/collab?${params}`,
      onMessage ?? (() => {}),
      onOpen,
    );
  }
}

export const api = new NexusClient();

// ── Reconnecting WebSocket ──────────────────────────────────

export interface ReconnectingSocket {
  send: (data: string) => void;
  close: () => void;
}

export function createReconnectingWebSocket(
  url: string,
  onMessage: (data: unknown) => void,
  onOpen?: () => void,
  options: {
    initialDelay?: number;
    maxDelay?: number;
    jitter?: number;
    maxRetries?: number;
  } = {},
): ReconnectingSocket {
  const initialDelay = options.initialDelay ?? 1000;
  const maxDelay = options.maxDelay ?? 30000;
  const jitter = options.jitter ?? 0.5;
  const maxRetries = options.maxRetries ?? Infinity;

  let ws: WebSocket | null = null;
  let stopped = false;
  let attempt = 0;
  let delay = initialDelay;
  let queue: string[] = [];

  function connect() {
    if (stopped) return;
    attempt++;

    ws = new WebSocket(url);

    ws.onopen = () => {
      delay = initialDelay;
      attempt = 0;
      for (const msg of queue) ws?.send(msg);
      queue = [];
      onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
        onMessage(event.data);
      }
    };

    ws.onclose = () => {
      if (stopped) return;
      if (attempt >= maxRetries) return;
      const jittered = delay * (1 + (Math.random() - 0.5) * jitter);
      const wait = Math.min(jittered, maxDelay);
      console.log(`[ws] reconnecting in ${Math.round(wait)}ms (attempt ${attempt})`);
      setTimeout(connect, wait);
      delay = Math.min(delay * 2, maxDelay);
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  connect();

  return {
    send(data: string) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(data);
      } else {
        queue.push(data);
      }
    },
    close() {
      stopped = true;
      ws?.close();
    },
  };
}
