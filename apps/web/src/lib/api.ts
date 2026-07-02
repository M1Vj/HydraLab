export type ApiErrorKind = "network" | "http" | "permission-denied" | "consent-required";

export type ApiError = {
  kind: ApiErrorKind;
  status?: number;
  message: string;
};

export class HydraApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(error: ApiError) {
    super(error.message);
    this.name = "HydraApiError";
    this.kind = error.kind;
    this.status = error.status;
  }
}

export type SourceRecord = {
  id: string;
  title: string;
  authors?: string;
  year?: string;
  url?: string;
  kind?: string;
  source_type?: string;
  doi?: string | null;
  arxiv_id?: string | null;
  metadata_json?: Record<string, unknown>;
  link_state?: string;
  trashed?: boolean;
  project_id?: string | null;
};

export type NoteRecord = {
  id: string;
  title: string;
  body?: string;
  source_id?: string | null;
  relative_path?: string;
  project_id?: string | null;
  updated_at?: number;
};

export type TaskRecord = {
  id: string;
  title: string;
  column: string;
  status?: string;
  detail?: string;
  progress?: number;
  position?: number;
  phase_indicator?: string;
  project_id?: string | null;
  due?: string | null;
  priority?: "low" | "normal" | "high" | "urgent" | string;
  tags?: string[];
  origin?: string;
  assistant_created?: boolean;
  lifecycle_state?: "active" | "draft" | "dismissed" | string;
  review_category?: string | null;
  trust_origin?: string;
};

export type TaskLinkRecord = {
  id: string;
  task_id: string;
  target_type: string;
  target_id_or_path: string;
  link_role: string;
  link_state: "live" | "source_trashed" | string;
};

export type GitChangedFile = { code: string; path: string };
export type GitStatusResponse = {
  is_repo: boolean;
  branch?: string | null;
  changed_files: GitChangedFile[];
  clean?: boolean;
};
export type GitCommit = { hash: string; author: string; at: string; subject: string };
export type GitCommitSuggestion = { message: string; files: string[] };

export type ConsoleRunResult = {
  status: "ran" | "rejected" | "blocked" | "disabled" | "approval_required" | string;
  command?: string;
  kind?: string;
  message?: string;
  output?: string;
  stderr?: string;
  returncode?: number;
  spawned?: boolean;
  approved_now?: string;
};

export type ConsoleAllowlist = {
  git_inspection: string[];
  verification: string[];
  offline: boolean;
};

export type ExportBundleFormat = {
  id: string;
  label: string;
  available: boolean;
  state?: string;
  message?: string;
};
export type ExportOptionsResponse = {
  citation_formats: string[];
  bundle_formats: ExportBundleFormat[];
  opt_in_categories: string[];
  excluded_by_default: string[];
};

export type ClaimRecord = {
  id: string;
  text: string;
  status?: string;
  location_type?: string | null;
  location_id?: string | null;
  link_state?: string;
  project_id?: string | null;
};

export type CitationRecord = {
  id: string;
  source_id: string;
  text: string;
  citation_key?: string;
  project_id?: string | null;
};

export type EvidenceRecord = {
  id: string;
  claim_id: string;
  citation_id?: string | null;
  source_id: string;
  passage: string;
  support: string;
  confidence: number;
  review_status?: string;
  source_title?: string;
  claim_text?: string;
};

export type ReviewItem = {
  id: string;
  item_type: string;
  title: string;
  summary?: string;
  origin_type?: string | null;
  origin_id?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  status?: string;
  payload?: Record<string, unknown>;
};

export type BrowserEventRecord = {
  id: string;
  project_id: string;
  url: string;
  title?: string;
  event_type?: string;
  detected_metadata?: Record<string, unknown>;
  created_at?: number;
};

export type ProjectObjectsResponse = {
  project_id: string;
  objects: {
    notes: NoteRecord[];
    sources: SourceRecord[];
    claims: ClaimRecord[];
    tasks: TaskRecord[];
    citations: CitationRecord[];
    evidence: EvidenceRecord[];
  };
  counts: Record<string, number>;
};

export type ProjectTreeNode = {
  id: string;
  path: string;
  name: string;
  type: "directory" | "file";
  parent: string;
  depth: number;
  size: number;
  modified_at: number;
  index_status: "indexed" | "needs-consent" | "excluded" | string;
};

export type ProjectTreeResponse = {
  root: string;
  nodes: ProjectTreeNode[];
  excluded: string[];
};

export type SourceDiscoveryRequest = {
  query: string;
  project_id?: string | null;
  offline_only?: boolean;
  scholarly_apis_enabled?: boolean;
  contact_email?: string;
};

export type SourceDiscoveryResult = {
  id?: string;
  title: string;
  authors?: string[] | string;
  year?: number | string | null;
  venue?: string | null;
  doi?: string | null;
  pdf_url?: string | null;
  pdf_available?: boolean;
  provider?: string;
  providers?: string[];
  confidence?: number;
  expected_size_bytes?: number | null;
  [key: string]: unknown;
};

export type SourceDiscoveryResponse = {
  state: "empty" | "loading" | "partial" | "failure" | "ready" | "offline" | string;
  results: SourceDiscoveryResult[];
  provider_statuses?: Array<{ provider: string; state: string; count?: number; error?: string }>;
  review_items?: ReviewItem[];
};

export type ActivityEventRecord = {
  id: string;
  kind: string;
  message: string;
  payload?: string;
  created_at: number;
};

export type ChatConversation = {
  id: string;
  title: string;
  created_at?: number;
};

export type ChatMessage = {
  id: string;
  conversation_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: number;
};

export type SettingsResponse = {
  provider_settings: Array<{
    provider: string;
    model: string;
    api_key_ref?: string;
    secret_ref?: string | null;
    auth_status?: string;
    resolved?: boolean;
  }>;
  workspace_preferences: Record<string, string>;
  global_settings: Record<string, unknown>;
};

export type ApiClient = {
  get<T>(path: string, init?: RequestInit): Promise<T>;
  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>;
  put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>;
  patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>;
  delete<T>(path: string, init?: RequestInit): Promise<T>;
  stream(path: string, body: unknown, onEvent: (event: unknown) => void, init?: RequestInit): Promise<void>;
};

const DEFAULT_TIMEOUT_MS = 12_000;

export const API_BASE_URL = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

export function createApiClient(baseUrl = API_BASE_URL, timeoutMs = DEFAULT_TIMEOUT_MS): ApiClient {
  async function request<T>(method: string, path: string, body?: unknown, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timer = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(resolvePath(baseUrl, path), {
        ...init,
        method,
        signal: init.signal ?? controller.signal,
        headers: {
          ...(body !== undefined ? { "content-type": "application/json" } : {}),
          ...init.headers,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!response.ok) {
        throw new HydraApiError(await normalizeHttpError(response));
      }
      if (response.status === 204) return undefined as T;
      const contentType = response.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) return (await response.json()) as T;
      return (await response.text()) as T;
    } catch (error) {
      if (error instanceof HydraApiError) throw error;
      throw new HydraApiError({
        kind: "network",
        message: error instanceof DOMException && error.name === "AbortError" ? "Request timed out" : "HydraLab backend is unavailable",
      });
    } finally {
      globalThis.clearTimeout(timer);
    }
  }

  return {
    get: (path, init) => request("GET", path, undefined, init),
    post: (path, body, init) => request("POST", path, body, init),
    put: (path, body, init) => request("PUT", path, body, init),
    patch: (path, body, init) => request("PATCH", path, body, init),
    delete: (path, init) => request("DELETE", path, undefined, init),
    stream: async (path, body, onEvent, init) => {
      const response = await fetch(resolvePath(baseUrl, path), {
        ...init,
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/event-stream", ...init?.headers },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new HydraApiError(await normalizeHttpError(response));
      if (!response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const dataLine = chunk.split("\n").find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          onEvent(JSON.parse(dataLine.slice(5).trim()));
        }
      }
    },
  };
}

async function normalizeHttpError(response: Response): Promise<ApiError> {
  let message = response.statusText || "Request failed";
  try {
    const payload = await response.json();
    const detail = payload.detail ?? payload.message;
    message = typeof detail === "string" ? detail : JSON.stringify(detail);
  } catch {
    message = await response.text().catch(() => message);
  }
  if (response.status === 401 || response.status === 403) {
    return {
      kind: message.includes("consent") || message.includes("user-initiated") ? "consent-required" : "permission-denied",
      status: response.status,
      message,
    };
  }
  return { kind: "http", status: response.status, message };
}

function resolvePath(baseUrl: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (baseUrl === "/api" && normalizedPath.startsWith("/api/")) {
    return normalizedPath;
  }
  return `${baseUrl}${normalizedPath}`;
}

export const api = createApiClient();
