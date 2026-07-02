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
  venue?: string;
  publisher?: string;
  csl_json?: Record<string, unknown>;
  keywords?: string[];
  identifiers?: Record<string, unknown>;
  duplicate_group_id?: string | null;
  duplicate_status?: string;
  merge_confidence?: number;
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

export type ClaimStatus = "draft" | "supported" | "weak" | "contradicted" | "needs_review" | "rejected";

export type ClaimRecord = {
  id: string;
  text: string;
  claim_text?: string;
  status?: ClaimStatus | string;
  claim_type?: string;
  location_type?: string | null;
  location_id?: string | null;
  extraction_mode?: string;
  origin_quote?: string;
  extraction_confidence?: number;
  link_state?: string;
  project_id?: string | null;
};

export type CitationRecord = {
  id: string;
  source_id: string;
  text: string;
  citation_key?: string;
  csl_json?: Record<string, unknown>;
  project_id?: string | null;
};

export type EvidenceLocator = {
  type?: string;
  page?: number;
  section?: string;
  paragraph?: number;
  fragment?: string;
};

export type EvidenceRecord = {
  id: string;
  claim_id: string;
  citation_id?: string | null;
  source_id: string;
  passage: string;
  support: string;
  support_level?: string;
  confidence: number;
  evidence_type?: string;
  quote_text?: string;
  locator?: EvidenceLocator;
  annotation_id?: string | null;
  sidecar_record_id?: string | null;
  review_status?: string;
  source_title?: string;
  claim_text?: string;
};

export type ClaimSuggestion = {
  claim_text: string;
  origin_quote: string;
  origin_ref?: string | null;
  location_type?: string | null;
  location_id?: string | null;
  extraction_confidence: number;
  extraction_mode: string;
  user_selected: boolean;
};

export type DuplicateVerdict = {
  left_id: string;
  right_id: string;
  status: "auto_merge" | "needs_review" | "flagged" | "none" | string;
  confidence: number;
  reason: string;
};

export type CitationRenderResponse = {
  style: string;
  processor: string;
  entries: string[];
};

export type SourceImportResponse = {
  imported: SourceRecord[];
  count: number;
  format: string;
};

export type RefIntFinding = {
  origin_type: string;
  origin_id: string;
  target_type: string;
  target_id: string;
  summary: string;
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
  chat_id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  context_refs?: ContextRef[];
  trust_origin?: string;
  created_at?: number;
};

export type Chat = {
  id: string;
  project_id: string;
  name: string;
  archived?: boolean;
  created_at?: number;
  updated_at?: number;
};

export type ContextRef = {
  type: string;
  id_or_path: string;
  locator?: Record<string, unknown>;
  label?: string;
  text?: string;
};

export type SendScopeItem = {
  type: string;
  id_or_path: string;
  label?: string;
  reason?: string;
  locator?: Record<string, unknown>;
};

export type SendScopeResult = {
  included: SendScopeItem[];
  excluded: SendScopeItem[];
  blocked: SendScopeItem[];
};

export type AssistantMode = { id: string; label: string; enabled: boolean; phase: number };

export type AssistantModes = {
  default_mode: string;
  full_access_enabled: boolean;
  modes: AssistantMode[];
  offline_only: boolean;
  g3_provider_send: boolean;
};

export type SkillInfo = {
  id: string;
  name: string;
  scope: string;
  enabled: boolean;
  risk_level: string;
  requires_approval: boolean;
  description?: string;
  disabled_reason?: string | null;
  body?: string;
  edited?: boolean;
  restorable?: boolean;
};

export type SkillsResponse = {
  skills: SkillInfo[];
  rejected_plugins: Array<{ path: string; reason: string }>;
};

export type AgentApproval = {
  id: string;
  action_kind: string;
  status: string;
  decision?: string | null;
  reason: string;
  trust_origin: string;
  target_kind?: string | null;
  target_ref?: string | null;
  summary: string;
};

export type AgentTraceStep = {
  index: number;
  kind: string;
  status: string;
  summary: string;
  tokens: number;
  trust_origin: string;
  skill_id?: string | null;
  capability?: string | null;
  denied_capability?: string | null;
};

export type AgentRunTrace = {
  run: { id: string; project_id: string; mode: string; status: string; paused: boolean };
  trace: { run_id: string; steps: AgentTraceStep[] };
  artifacts?: AgentRunArtifact[];
};

export type AgentRunArtifact = {
  id: string;
  kind: string;
  ref?: string;
  summary?: string;
  stage?: string;
  method?: string;
  ranking?: Array<{ id: string; title?: string; score: number }>;
};

export type OrchestratorStage = {
  id: string;
  label: string;
  enabled: boolean;
};

export type OrchestratorRunSummary = {
  id: string;
  project_id: string;
  mode: string;
  status: string;
  state?: string;
  paused: boolean;
  tokens_used?: number;
  created_at?: number;
};

export type OrchestratorRunResponse = AgentRunTrace & {
  run: AgentRunTrace["run"] & { state?: string };
  artifacts: AgentRunArtifact[];
};

export type IdeaRubricResult = {
  criterion: string;
  value: number;
  rationale: string;
  stage_run_id: string;
  source_refs: string[];
};

export type IdeaEvidenceLink = {
  source_id: string;
  evidence_id?: string;
  kind?: string;
};

export type IdeaCandidate = {
  id: string;
  run_id: string;
  title: string;
  short_hypothesis: string;
  research_question: string;
  motivation: string;
  method_sketch: string;
  expected_contribution: string;
  required_sources: string[];
  evidence_links: IdeaEvidenceLink[];
  novelty_claim: string;
  feasibility_notes: string;
  risks: string;
  estimated_effort: string;
  generated_by_stage: string;
  parent_candidate_id?: string | null;
  status: string;
  critique: Record<string, string[]>;
  rubric_results: IdeaRubricResult[];
  rank?: number | null;
  trust_origin: string;
};

export type IdeaRunResponse = {
  run: {
    id: string;
    project_id: string;
    mode: string;
    status: string;
    state?: string;
    paused: boolean;
    recipe?: string;
    inputs?: Array<Record<string, string>>;
  };
  trace: { run_id: string; steps: AgentTraceStep[] };
  artifacts: AgentRunArtifact[];
  candidates: IdeaCandidate[];
};

export type IdeaPromotionResponse = {
  review_item_id?: string | null;
  status: string;
  created_target_id?: string | null;
  created_target_kind?: string;
};

export type ContextFileInfo = {
  name: string;
  path: string;
  content: string;
  scope: string;
  recovery: string;
  exists: boolean;
  visible?: boolean;
};

export type ContextFilesResponse = {
  profile_id: string;
  global_files: ContextFileInfo[];
  project_file: ContextFileInfo;
};

export type ContextFileChange = {
  id: string;
  file: string;
  change_type: string;
  timing: string;
  criticality: string;
  trust_level: string;
  provenance: string;
  summary: string;
  checkpoint_ref?: string | null;
  logs_only: boolean;
  recovery: string;
  created_at: number;
};

export type McpToolInfo = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  permission: "allow" | "deny" | string;
  read_only: boolean;
  status: "allowed" | "disabled" | string;
};

export type McpServerInfo = {
  id: string;
  name: string;
  transport?: string;
  enabled: boolean;
  connector?: string | null;
  status: "registered" | "connected" | "failed" | string;
  connection_error: string;
  auth_handle_ref?: string | null;
  state: "empty" | "loading" | "failure" | "permission-denied" | "ready" | string;
  tools: McpToolInfo[];
};

export type McpServersResponse = { servers: McpServerInfo[] };

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

// --- Citation / claim / evidence typed endpoints (branch 01-09) -------------

export function importSources(
  input: { format: "bibtex" | "ris" | "csl-json"; content: string; project_id?: string | null },
  client: ApiClient = api,
): Promise<SourceImportResponse> {
  return client.post<SourceImportResponse>("/api/sources/import", input);
}

export function renderCitations(
  input: { source_ids?: string[]; style?: string; manuscript?: string; html?: boolean },
  client: ApiClient = api,
): Promise<CitationRenderResponse> {
  return client.post<CitationRenderResponse>("/api/citations/render", input);
}

export function detectClaimCandidates(
  input: { text: string; location_type?: string; location_id?: string; origin_ref?: string; auto_create?: boolean },
  client: ApiClient = api,
): Promise<{ suggestions: ClaimSuggestion[]; created_claims: ClaimRecord[]; committed: boolean }> {
  return client.post("/api/claims/detect", input);
}

export function promoteClaim(
  claimId: string,
  input: { status: ClaimStatus; reviewed?: boolean },
  client: ApiClient = api,
): Promise<ClaimRecord> {
  return client.patch<ClaimRecord>(`/api/claims/${encodeURIComponent(claimId)}`, input);
}

export function detectDuplicateSources(projectId?: string, client: ApiClient = api): Promise<{ duplicates: DuplicateVerdict[] }> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return client.post(`/api/sources/duplicates${query}`);
}

export function mergeSources(
  input: { source_ids: string[]; reason?: "exact_identifier" | "exact_hash" | "user_confirmed_fuzzy"; merge_confidence?: number },
  client: ApiClient = api,
): Promise<{ survivor_id: string; merged_ids: string[]; merge_record_id: string }> {
  return client.post("/api/sources/merge", input);
}

export function scanReferentialIntegrity(projectId?: string, client: ApiClient = api): Promise<{ findings: RefIntFinding[]; count: number }> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return client.post(`/api/refint/scan${query}`);
}

// --- Writing / manuscript formats / DOCX (branch 01-12) ---------------------

export type ManuscriptFormat = {
  citation_style: string;
  font_family: string;
  font_size: string;
  line_spacing: number;
  paragraph_spacing: string;
  margins: string;
  page_size: string;
  orientation: string;
  heading_numbering: boolean;
  title_page: boolean;
  abstract: boolean;
  columns: number;
  figure_caption: string;
  table_caption: string;
  reference_format: string;
  page_numbers: boolean;
  headers_footers: boolean;
  manuscript_template: string;
  docx_template: string;
};

export type ManuscriptFormatResponse = {
  manuscript: string;
  format: ManuscriptFormat;
  validation_error: { key: string; message: string } | null;
  source: "global" | "merged" | string;
};

export type DocxAvailabilityResponse = {
  adapter: string;
  version: string;
  availability_status: "available" | "unavailable" | string;
  available: boolean;
  setup_error: string;
};

export type LatexAvailabilityResponse = {
  available: boolean;
  toolchain: string;
  path: string;
  setup_error: string;
};

export type DocxImportResponse = {
  status: string;
  content: string;
  metadata: Record<string, string>;
  flagged_active_content: string[];
};

export type ManuscriptExportResponse = {
  status: string;
  output_path: string | null;
  format: ManuscriptFormat;
};

export function listManuscripts(client: ApiClient = api): Promise<{ manuscripts: string[] }> {
  return client.get("/api/writing/manuscripts");
}

export function getFormatDefaults(client: ApiClient = api): Promise<{ defaults: ManuscriptFormat }> {
  return client.get("/api/writing/format-defaults");
}

export function getManuscriptFormat(manuscript: string, client: ApiClient = api): Promise<ManuscriptFormatResponse> {
  return client.get(`/api/writing/manuscripts/${encodeURIComponent(manuscript)}/format`);
}

export function getDocxAvailability(client: ApiClient = api): Promise<DocxAvailabilityResponse> {
  return client.get("/api/writing/docx/availability");
}

export function getLatexAvailability(client: ApiClient = api): Promise<LatexAvailabilityResponse> {
  return client.get("/api/writing/latex/availability");
}

export function exportManuscript(
  manuscript: string,
  input: { source_file: string; output_name?: string; include_bibliography?: boolean; project_id?: string | null },
  client: ApiClient = api,
): Promise<ManuscriptExportResponse> {
  return client.post(`/api/writing/manuscripts/${encodeURIComponent(manuscript)}/export`, input);
}

// --- DOCX OpenXML assisted edits (branch 02-08, Phase 2) --------------------

export type DocxOpType =
  | "replace_text"
  | "insert_paragraph"
  | "apply_style"
  | "update_table"
  | "update_citation"
  | "comment"
  | "delete"
  | "other";
export type DocxReviewStatus = "pending" | "approved" | "rejected";
export type DocxValidationStatus = "unvalidated" | "valid" | "invalid";
export type DocxRiskLabel = "low" | "medium" | "high";

export type DocxEditOperation = {
  id: string;
  plan_id: string;
  op_type: DocxOpType | string;
  target_locator: string;
  location_label: string;
  before_summary: string;
  after_summary: string;
  payload: Record<string, unknown>;
  risk_label: DocxRiskLabel | string;
  review_status: DocxReviewStatus | string;
  validation_status: DocxValidationStatus | string;
  applied: boolean;
  trust_level: string;
  motivating_excerpt?: string;
};

export type DocxEditPlan = {
  id: string;
  manuscript: string;
  target_relpath: string;
  status: "draft" | "applied" | "rolled_back" | "failed" | string;
  mode: string;
  trust_level: string;
  checkpoint_ref?: string | null;
};

export type DocxEditPlanResponse = {
  plan: DocxEditPlan;
  operations: DocxEditOperation[];
  review_inbox?: unknown[];
  downgrade_log?: unknown[];
};

export type DocxEditProposalInput = {
  op_type: DocxOpType | string;
  target_locator?: string;
  payload?: Record<string, unknown>;
  justification?: string;
  justification_source?: "assistant" | "document";
  motivating_excerpt?: string;
};

export function createDocxEditPlan(
  input: {
    manuscript: string;
    source_file: string;
    mode?: "passive" | "copilot" | "full_access";
    project_id?: string | null;
    proposals: DocxEditProposalInput[];
  },
  client: ApiClient = api,
): Promise<DocxEditPlanResponse> {
  return client.post("/api/writing/docx/edit-plan", input);
}

export function getDocxEditPlan(planId: string, client: ApiClient = api): Promise<DocxEditPlanResponse> {
  return client.get(`/api/writing/docx/edit-plan/${encodeURIComponent(planId)}`);
}

export function reviewDocxOperation(
  planId: string,
  operationId: string,
  decision: DocxReviewStatus,
  client: ApiClient = api,
): Promise<{ operation: DocxEditOperation }> {
  return client.post(
    `/api/writing/docx/edit-plan/${encodeURIComponent(planId)}/operations/${encodeURIComponent(operationId)}/review`,
    { decision },
  );
}

export function applyDocxEditPlan(planId: string, client: ApiClient = api): Promise<DocxEditPlanResponse> {
  return client.post(`/api/writing/docx/edit-plan/${encodeURIComponent(planId)}/apply`);
}

export function rollbackDocxEditPlan(planId: string, client: ApiClient = api): Promise<DocxEditPlanResponse> {
  return client.post(`/api/writing/docx/edit-plan/${encodeURIComponent(planId)}/rollback`);
}
