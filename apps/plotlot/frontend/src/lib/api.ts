/**
 * API client for PlotLot backend.
 *
 * In development: proxies through Next.js API routes → FastAPI at localhost:8000
 * In production: proxies through Vercel edge → Render backend
 */

export interface PipelineStatus {
  step: string;
  message: string;
  complete?: boolean;
  resolved_address?: string;
  folio?: string;
  lot_sqft?: number;
}

export interface ThinkingEvent {
  step: string;
  thoughts: string[];
}

export type AgentTaskStatus = "queued" | "running" | "complete" | "attention";

export interface AgentTaskEvent {
  type?: "task_start" | "task_update" | "task_complete";
  task_id?: string;
  task_type?: string;
  name?: string;
  title?: string;
  detail?: string;
  status?: AgentTaskStatus;
  percent?: number;
  duration_ms?: number;
  url?: string | null;
  screenshot_b64?: string | null;
  citations?: string[];
}

export interface BrowserActionEvent {
  type?: "browser_action" | "browser_navigate" | "browser_click" | "browser_type" | "browser_extract";
  action?: string;
  url?: string | null;
  selector?: string | null;
  value?: string | null;
  screenshot_b64?: string | null;
  screenshot_url?: string | null;
  extracted_text?: string | null;
  timestamp?: string;
  duration_ms?: number;
}

export interface ReasoningEvent {
  phase?: "understand" | "recall" | "plan" | "execute" | "synthesize" | string;
  step?: string;
  summary?: string;
  thoughts?: string[];
  confidence?: number;
  alternatives?: string[];
}

export type AnalysisErrorType =
  | "timeout"
  | "bad_address"
  | "backend_unavailable"
  | "pipeline_error"
  | "network_error"
  | "unknown"
  | "geocoding_failed"
  | "low_accuracy";

export interface AnalysisError {
  detail: string;
  errorType: AnalysisErrorType;
}

export type DealType = "land_deal" | "wholesale" | "creative_finance" | "hybrid";

export interface AnalysisOptions {
  address: string;
  dealType?: DealType;
  skipSteps?: string[];
}

export interface SetbacksData {
  front: string;
  side: string;
  rear: string;
}

export interface ConstraintData {
  name: string;
  max_units: number;
  raw_value: number;
  formula: string;
  is_governing: boolean;
}

export interface DensityAnalysisData {
  max_units: number;
  governing_constraint: string;
  constraints: ConstraintData[];
  lot_size_sqft: number;
  buildable_area_sqft: number | null;
  lot_width_ft: number | null;
  lot_depth_ft: number | null;
  max_gla_sqft: number | null;
  confidence: string;
  notes: string[];
}

export interface NumericParamsData {
  max_density_units_per_acre: number | null;
  min_lot_area_per_unit_sqft: number | null;
  far: number | null;
  max_lot_coverage_pct: number | null;
  max_height_ft: number | null;
  max_stories: number | null;
  setback_front_ft: number | null;
  setback_side_ft: number | null;
  setback_rear_ft: number | null;
  min_unit_size_sqft: number | null;
  min_lot_width_ft: number | null;
  parking_spaces_per_unit: number | null;
  property_type: string | null;
  parking_per_1000_gla_sqft: number | null;
  max_gla_sqft: number | null;
  min_tenant_size_sqft: number | null;
  loading_spaces: number | null;
}

export interface PropertyRecordData {
  folio: string;
  address: string;
  municipality: string;
  county: string;
  owner: string;
  zoning_code: string;
  zoning_description: string;
  land_use_code: string;
  land_use_description: string;
  lot_size_sqft: number;
  lot_dimensions: string;
  bedrooms: number;
  bathrooms: number;
  half_baths: number;
  floors: number;
  living_units: number;
  building_area_sqft: number;
  living_area_sqft: number;
  year_built: number;
  assessed_value: number;
  market_value: number;
  last_sale_price: number;
  last_sale_date: string;
  lat: number | null;
  lng: number | null;
  parcel_geometry?: number[][] | null;
  zoning_layer_url?: string;
}

export interface ComparableSaleData {
  address: string;
  sale_price: number;
  sale_date: string;
  lot_size_sqft: number;
  zoning_code: string;
  distance_miles: number;
  price_per_acre: number;
  price_per_unit: number | null;
  adjustments: Record<string, number>;
}

export interface CompAnalysisData {
  comparables: ComparableSaleData[];
  median_price_per_acre: number;
  estimated_land_value: number;
  adv_per_unit: number | null;
  confidence: number;
}

export interface LandProFormaData {
  gross_development_value: number;
  hard_costs: number;
  soft_costs: number;
  builder_margin: number;
  max_land_price: number;
  cost_per_door: number;
  construction_cost_psf: number;
  avg_unit_size_sqft: number;
  adv_per_unit: number;
  max_units: number;
  soft_cost_pct: number;
  builder_margin_pct: number;
  notes: string[];
}

export interface SourceRefData {
  section: string;
  section_title: string;
  chunk_text_preview: string;
  score: number;
}

export interface DossierLotFactsData {
  lot_size_sqft: number | null;
  lot_dimensions: string;
  lot_width_ft: number | null;
  lot_depth_ft: number | null;
}

export interface DossierDimensionalStandardsData {
  setbacks: SetbacksData;
  max_height: string;
  max_density: string;
  floor_area_ratio: string;
  lot_coverage: string;
  min_lot_size: string;
  parking_requirements: string;
}

export interface DossierEvidenceRefData {
  kind: string;
  label: string;
  source: string;
  preview: string;
  confidence: string;
}

export interface ActivePropertyDossierData {
  resolved_address: string;
  parcel_id: string;
  municipality: string;
  county: string;
  state: string;
  zoning_district: string;
  zoning_description: string;
  lot_facts: DossierLotFactsData;
  dimensional_standards: DossierDimensionalStandardsData;
  max_units: number | null;
  governing_constraint: string;
  evidence_refs: DossierEvidenceRefData[];
  confidence: string;
  freshness_timestamp: string;
}

export interface ZoningReportData {
  address: string;
  formatted_address: string;
  municipality: string;
  county: string;
  lat: number | null;
  lng: number | null;
  zoning_district: string;
  zoning_description: string;
  allowed_uses: string[];
  conditional_uses: string[];
  prohibited_uses: string[];
  setbacks: SetbacksData;
  max_height: string;
  max_density: string;
  floor_area_ratio: string;
  lot_coverage: string;
  min_lot_size: string;
  parking_requirements: string;
  property_record: PropertyRecordData | null;
  numeric_params: NumericParamsData | null;
  density_analysis: DensityAnalysisData | null;
  comp_analysis: CompAnalysisData | null;
  pro_forma: LandProFormaData | null;
  summary: string;
  sources: string[];
  confidence: string;
  source_refs?: SourceRefData[];
  confidence_warning?: string;
  suggested_next_steps?: string[];
  active_dossier?: ActivePropertyDossierData | null;
}

export interface RuntimeCapabilityDetail {
  ready: boolean;
  reason?: string;
  blocked_by?: string[];
  dependencies?: string[];
}

export interface RuntimeHealthData {
  status: "healthy" | "degraded";
  checks: Record<string, string>;
  capabilities?: {
    db_backed_analysis_ready?: boolean;
    portfolio_ready?: boolean;
    agent_chat_ready?: boolean;
  };
  capability_details?: {
    db_backed_analysis_ready?: RuntimeCapabilityDetail;
    portfolio_ready?: RuntimeCapabilityDetail;
    agent_chat_ready?: RuntimeCapabilityDetail;
  };
  runtime?: {
    startup_mode?: string;
    startup_warnings?: string[];
  };
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchRuntimeHealth(): Promise<RuntimeHealthData> {
  const response = await fetch(`${API_BASE}/health`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health request failed with HTTP ${response.status}`);
  }

  return response.json();
}

/** Extract a human-readable error message from a FastAPI error response. */
function extractErrorMessage(err: { detail?: unknown }, status: number): string {
  const detail = err.detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ");
  }
  if (typeof detail === "string") return detail;
  return `HTTP ${status}`;
}

/**
 * Stream zoning analysis with real-time pipeline progress.
 * Uses Server-Sent Events for step-by-step updates.
 * Auto-retries once on network failure (not on backend error events).
 */
export async function streamAnalysis(
  options: AnalysisOptions,
  onStatus: (status: PipelineStatus) => void,
  onResult: (report: ZoningReportData) => void,
  onError: (error: AnalysisError) => void,
  onThinking?: (event: ThinkingEvent) => void,
  onSuggestions?: (suggestions: string[]) => void,
  onRetry?: (attempt: number) => void,
): Promise<void> {
  const maxRetries = 1;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    try {
      const response = await fetch(`${API_BASE}/api/v1/analyze/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: options.address,
          deal_type: options.dealType || "land_deal",
          skip_steps: options.skipSteps || [],
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Request failed" }));
        onError({
          detail: extractErrorMessage(err, response.status),
          errorType: "pipeline_error",
        });
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onError({ detail: "No response stream available", errorType: "unknown" });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "";
      let eventData = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            eventData = line.slice(6).trim();
          } else if (line === "" && eventType && eventData) {
            try {
              const parsed = JSON.parse(eventData);
              if (eventType === "status") {
                onStatus(parsed as PipelineStatus);
              } else if (eventType === "result") {
                onResult(parsed as ZoningReportData);
              } else if (eventType === "thinking") {
                onThinking?.(parsed as ThinkingEvent);
              } else if (eventType === "suggestions") {
                onSuggestions?.(parsed.suggestions || []);
              } else if (eventType === "error") {
                onError({
                  detail: parsed.detail || "Unknown error",
                  errorType: (parsed.error_type || "unknown") as AnalysisErrorType,
                });
              }
            } catch {
              // Skip malformed events
            }
            eventType = "";
            eventData = "";
          }
        }
      }
      return; // Success — exit retry loop
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        onError({
          detail: "Request timed out after 2 minutes. The server may be starting up \u2014 try again.",
          errorType: "timeout",
        });
        return;
      }
      // Network error — retry if we have attempts left
      if (attempt < maxRetries) {
        onRetry?.(attempt + 1);
        await new Promise((r) => setTimeout(r, 2000));
        continue;
      }
      onError({
        detail: "Connection failed. The server may be starting up \u2014 try again in a moment.",
        errorType: "network_error",
      });
    } finally {
      clearTimeout(timeoutId);
    }
  }
}

/**
 * Non-streaming analysis — simple POST, wait for full result.
 */
export async function analyzeAddress(address: string): Promise<ZoningReportData> {
  const response = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Chat (Phase 5c)
// ---------------------------------------------------------------------------

export interface ChatMessageData {
  role: "user" | "assistant";
  content: string;
}

export interface ToolUseEvent {
  tool: string;
  args: Record<string, string>;
  message: string;
}

export interface ToolResultEvent {
  tool: string;
  status?: string;
}

/**
 * Stream a chat response with token-by-token delivery.
 * Handles tool use events and session persistence.
 */
export async function streamChat(
  message: string,
  history: ChatMessageData[],
  reportContext: ZoningReportData | null,
  onToken: (token: string) => void,
  onDone: (fullContent: string) => void,
  onError: (error: string) => void,
  sessionId?: string | null,
  onSession?: (sessionId: string) => void,
  onToolUse?: (event: ToolUseEvent) => void,
  onToolResult?: (event: ToolResultEvent) => void,
  onThinking?: (event: ThinkingEvent) => void,
  onTaskEvent?: (event: AgentTaskEvent) => void,
  onBrowserAction?: (event: BrowserActionEvent) => void,
  onReasoning?: (event: ReasoningEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history,
        report_context: reportContext,
        session_id: sessionId || undefined,
      }),
      signal,
    });
  } catch {
    if (signal?.aborted) return;
    onError("Connection failed. Is the backend running?");
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Request failed" }));
    onError(extractErrorMessage(err, response.status));
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError("No response stream available");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let eventType = "";
  let eventData = "";

  const dispatchParsedEvent = (type: string, data: string) => {
    try {
      const parsed = JSON.parse(data);
      if (type === "session") {
        onSession?.(parsed.session_id);
      } else if (type === "token") {
        onToken(parsed.content);
      } else if (type === "thinking") {
        onThinking?.(parsed as ThinkingEvent);
      } else if (type === "reasoning") {
        const reasoning = parsed as ReasoningEvent;
        if (onReasoning) {
          onReasoning(reasoning);
        } else {
          const thought =
            reasoning.summary ||
            reasoning.thoughts?.join(" ") ||
            "Reasoning through the current land-use task.";
          onThinking?.({
            step: reasoning.phase || reasoning.step || "reasoning",
            thoughts: [thought],
          });
        }
      } else if (type === "tool_use") {
        onToolUse?.(parsed as ToolUseEvent);
      } else if (type === "tool_result") {
        onToolResult?.(parsed as ToolResultEvent);
      } else if (
        type === "task_start" ||
        type === "task_update" ||
        type === "task_complete"
      ) {
        onTaskEvent?.({ ...(parsed as AgentTaskEvent), type });
      } else if (
        type === "browser_action" ||
        type === "browser_navigate" ||
        type === "browser_click" ||
        type === "browser_type" ||
        type === "browser_extract"
      ) {
        onBrowserAction?.({ ...(parsed as BrowserActionEvent), type });
      } else if (type === "done") {
        onDone(parsed.full_content);
      } else if (type === "error") {
        onError(parsed.detail || "Unknown error");
      }
    } catch {
      // Skip malformed events
    }
  };

  const processSseLine = (line: string) => {
    if (line.startsWith("event: ")) {
      eventType = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      eventData = line.slice(6).trim();
    } else if (line === "" && eventType && eventData) {
      dispatchParsedEvent(eventType, eventData);
      eventType = "";
      eventData = "";
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        processSseLine(line);
      }
    }
  } catch {
    if (signal?.aborted) return;
    onError("Connection interrupted while streaming the chat response.");
    return;
  }

  if (buffer) {
    processSseLine(buffer);
  }
  if (eventType && eventData) {
    dispatchParsedEvent(eventType, eventData);
  }
}

// ---------------------------------------------------------------------------
// Portfolio (Phase 5b)
// ---------------------------------------------------------------------------

export interface SavedAnalysis {
  id: string;
  address: string;
  municipality: string;
  county: string;
  zoning_district: string;
  max_units: number | null;
  confidence: string;
  saved_at: string;
  report: ZoningReportData;
}

export async function saveAnalysis(report: ZoningReportData): Promise<SavedAnalysis> {
  const response = await fetch(`${API_BASE}/api/v1/portfolio`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Save failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  return response.json();
}

export async function listPortfolio(): Promise<SavedAnalysis[]> {
  const response = await fetch(`${API_BASE}/api/v1/portfolio`);
  if (!response.ok) throw new Error("Failed to load portfolio");
  return response.json();
}

export async function deleteFromPortfolio(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/portfolio/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed to delete");
}

// ---------------------------------------------------------------------------
// Building Render (AI-generated architectural visualization)
// ---------------------------------------------------------------------------

export interface BuildingViewImage {
  view: string;  // "front", "aerial", "side"
  image_base64: string;
  prompt_used: string;
}

export interface BuildingRenderData {
  views: BuildingViewImage[];
  cached: boolean;
  generation_time_ms: number;
}

export interface BuildingRenderParams {
  property_type: string;
  stories: number;
  total_width_ft: number;
  total_depth_ft: number;
  max_height_ft: number;
  lot_width_ft: number;
  lot_depth_ft: number;
  zoning_district: string;
  unit_count: number;
  setback_front_ft: number;
  setback_side_ft: number;
  setback_rear_ft: number;
  municipality?: string;
}

export async function renderBuilding(params: BuildingRenderParams): Promise<BuildingRenderData> {
  const response = await fetch(`${API_BASE}/api/v1/render/building`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Render failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Document Generation (Clause Builder)
// ---------------------------------------------------------------------------

export interface DocumentTemplateInfo {
  document_type: string;
  label: string;
  description: string;
  supported_deal_types: string[];
  supported_formats: string[];
  required_fields: string[];
  optional_fields: string[];
}

export interface DocumentGenerateParams {
  document_type: string;
  deal_type: string;
  context: Record<string, string | number>;
  output_format?: string;
}

export interface DocumentPreviewClause {
  id: string;
  title: string;
  content: string;
}

export interface DocumentPreviewData {
  document_type: string;
  deal_type: string;
  clause_count: number;
  clauses: DocumentPreviewClause[];
}

export async function listDocumentTemplates(): Promise<DocumentTemplateInfo[]> {
  const response = await fetch(`${API_BASE}/api/v1/documents/templates`);
  if (!response.ok) throw new Error("Failed to load document templates");
  return response.json();
}

export async function previewDocument(params: DocumentGenerateParams): Promise<DocumentPreviewData> {
  const response = await fetch(`${API_BASE}/api/v1/documents/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Preview failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  return response.json();
}

export async function generateDocument(params: DocumentGenerateParams): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/v1/documents/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Generation failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  return response.blob();
}

// ---------------------------------------------------------------------------
// Workspace Harness
// ---------------------------------------------------------------------------

export interface WorkspaceData {
  id: string;
  name: string;
  slug: string;
  created_at?: string | null;
}

export interface ProjectData {
  id: string;
  workspace_id: string;
  name: string;
  project_type: string;
  status: string;
  criteria: Record<string, unknown>;
  created_at?: string | null;
}

export interface SiteData {
  id: string;
  project_id: string;
  label: string;
  address?: string | null;
  parcel_id?: string | null;
  lat?: number | null;
  lng?: number | null;
  score?: number | null;
  site_type: string;
  created_at?: string | null;
}

export interface EvidenceItemData {
  id: string;
  workspace_id?: string | null;
  project_id?: string | null;
  site_id?: string | null;
  analysis_run_id?: string | null;
  claim_key: string;
  value: Record<string, unknown>;
  source_type: string;
  source_url?: string | null;
  source_title?: string | null;
  tool_name: string;
  confidence: string;
  created_at?: string | null;
}

export interface HarnessRunRequest {
  workspace_id?: string | null;
  project_id?: string | null;
  site_id?: string | null;
  skill?: string | null;
  intent?: string | null;
  prompt: string;
  payload?: Record<string, unknown>;
}

export interface HarnessRunResult {
  status: string;
  summary: string;
  data: Record<string, unknown>;
  evidence_ids: string[];
  open_questions: string[];
  next_actions: string[];
}

export interface McpToolContract {
  name: string;
  description: string;
  risk_class?: string;
  input_schema: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
}

export interface McpToolListResult {
  tools: McpToolContract[];
}

export interface McpInvokeResult {
  status: string;
  tool: string;
  result: Record<string, unknown>;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  return response.json();
}

export function listWorkspaces(): Promise<WorkspaceData[]> {
  return requestJson<WorkspaceData[]>("/api/v1/workspaces");
}

export function createWorkspace(params: { name: string; slug?: string }): Promise<WorkspaceData> {
  return requestJson<WorkspaceData>("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function listWorkspaceProjects(workspaceId: string): Promise<ProjectData[]> {
  return requestJson<ProjectData[]>(`/api/v1/workspaces/${workspaceId}/projects`);
}

export function createProject(params: {
  workspace_id: string;
  name: string;
  project_type?: string;
  criteria?: Record<string, unknown>;
}): Promise<ProjectData> {
  return requestJson<ProjectData>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function listProjectSites(projectId: string): Promise<SiteData[]> {
  return requestJson<SiteData[]>(`/api/v1/projects/${projectId}/sites`);
}

export function createSite(params: {
  project_id: string;
  label: string;
  address?: string;
  parcel_id?: string;
  lat?: number;
  lng?: number;
  site_type?: string;
}): Promise<SiteData> {
  return requestJson<SiteData>("/api/v1/sites", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function listProjectEvidence(projectId: string): Promise<EvidenceItemData[]> {
  return requestJson<EvidenceItemData[]>(`/api/v1/projects/${projectId}/evidence`);
}

export function runHarness(params: HarnessRunRequest): Promise<HarnessRunResult> {
  return requestJson<HarnessRunResult>("/api/v1/harness/run", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function listMcpTools(): Promise<McpToolListResult> {
  return requestJson<McpToolListResult>("/api/v1/mcp/tools");
}

export function invokeMcpTool(name: string, input: Record<string, unknown>): Promise<McpInvokeResult> {
  return requestJson<McpInvokeResult>("/api/v1/mcp/invoke", {
    method: "POST",
    body: JSON.stringify({ name, input }),
  });
}
