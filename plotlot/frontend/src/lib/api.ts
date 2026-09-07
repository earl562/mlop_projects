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
  // Data center scoring
  composite_score?: number;
  composite_rating?: string;
  chunk_count?: number;
}

export interface ThinkingEvent {
  step: string;
  thoughts: string[];
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

export interface FloodZoneData {
  zone: string;
  zone_subtype: string;
  in_sfha: boolean;
  risk_level: string;
  description: string;
}

export interface WetlandData {
  wetland_type: string;
  acres: number;
}

export interface SiteRiskData {
  flood_zone: FloodZoneData | null;
  wetlands: WetlandData[];
  has_wetlands: boolean;
  overall_risk: string;
  risk_flags: string[];
  data_sources: string[];
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
  site_risk: SiteRiskData | null;
  summary: string;
  sources: string[];
  confidence: string;
  source_refs?: SourceRefData[];
  confidence_warning?: string;
  suggested_next_steps?: string[];
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

export type ToolRiskClass =
  | "read_only"
  | "expensive_read"
  | "write_internal"
  | "write_external"
  | "execution";

export interface McpToolContract {
  name: string;
  description: string;
  risk_class: ToolRiskClass;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  timeout_seconds: number;
  budget_cents: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const STREAM_TIMEOUT_MS = 120_000;
const FIRST_EVENT_TIMEOUT_MS = 15_000;
const CHAT_STREAM_IDLE_TIMEOUT_MS = 30_000;
const NETWORK_FAILURE_DETAIL = "Connection failed. The server may be starting up — try again in a moment.";
const BACKEND_UNAVAILABLE_DETAIL =
  "Analysis is temporarily unavailable because the data backend is offline. Please try again shortly.";
const STREAM_TIMEOUT_DETAIL =
  "Request timed out after 2 minutes. The server may be starting up — try again.";
const ANALYSIS_INCOMPLETE_DETAIL =
  "The analysis stream ended before a final result was returned.";
const CHAT_INCOMPLETE_DETAIL =
  "The response stream ended before completion. Please try again.";
const CHAT_INVALID_DETAIL =
  "The response stream sent invalid data. Please try again.";
const CHAT_CANCELLED_DETAIL =
  "The response was cancelled. Please try again.";
const CHAT_TIMEOUT_DETAIL =
  "The response timed out. Please try again.";
const CHAT_CONNECTION_DETAIL =
  "The response connection was interrupted. Please try again.";

class SseProtocolError extends Error {}

class SseReadTimeoutError extends Error {}

interface ConsumeSseOptions {
  readTimeoutMs?: () => number | undefined;
  onActivity?: () => void;
}

async function consumeSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (eventType: string, parsed: unknown) => boolean,
  options: ConsumeSseOptions = {},
): Promise<boolean> {
  const decoder = new TextDecoder();
  let buffer = "";
  let eventType = "";
  let dataLines: string[] = [];
  let terminalSeen = false;

  const dispatchEvent = () => {
    if (!eventType || dataLines.length === 0) return;
    const rawData = dataLines.join("\n");
    eventType = eventType.trim();
    dataLines = [];

    if (terminalSeen) {
      eventType = "";
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(rawData);
    } catch {
      throw new SseProtocolError(CHAT_INVALID_DETAIL);
    }

    terminalSeen = onEvent(eventType, parsed);
    eventType = "";
  };

  const processLine = (rawLine: string) => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    } else if (line === "") {
      dispatchEvent();
    }
  };

  while (true) {
    const timeoutMs = options.readTimeoutMs?.();
    const readResult = timeoutMs
      ? Promise.race([
          reader.read(),
          new Promise<never>((_, reject) => {
            setTimeout(
              () => reject(new SseReadTimeoutError("SSE_READ_TIMEOUT")),
              timeoutMs,
            );
          }),
        ])
      : reader.read();
    const { done, value } = await readResult;
    if (done) break;

    options.onActivity?.();
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) processLine(line);
  }

  buffer += decoder.decode();
  if (buffer) processLine(buffer);
  dispatchEvent();
  return terminalSeen;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isStreamStartupTimeout(error: unknown): boolean {
  return error instanceof SseReadTimeoutError;
}

function isDbBackedAnalysisReady(health: RuntimeHealthData): boolean {
  const capabilityReady = health.capabilities?.db_backed_analysis_ready;
  const detailReady = health.capability_details?.db_backed_analysis_ready?.ready;

  if (typeof capabilityReady === "boolean") return capabilityReady;
  if (typeof detailReady === "boolean") return detailReady;
  return health.status === "healthy";
}

function normalizeAnalysisError(detail: string, fallbackType: AnalysisErrorType): AnalysisError {
  const lowered = detail.toLowerCase();

  if (
    lowered.includes("backend is offline") ||
    lowered.includes("temporarily unavailable") ||
    lowered.includes("database_unavailable")
  ) {
    return { detail, errorType: "backend_unavailable" };
  }

  if (lowered.includes("timed out")) {
    return { detail, errorType: "timeout" };
  }

  if (lowered.includes("could not geocode") || lowered.includes("geocoding")) {
    return { detail, errorType: "geocoding_failed" };
  }

  return { detail, errorType: fallbackType };
}

async function recoverFromStreamFailure(
  options: AnalysisOptions,
  onResult: (report: ZoningReportData) => void,
  fallbackDetail: string,
): Promise<AnalysisError | null> {
  const health = await fetchRuntimeHealth().catch(() => null);

  if (health && !isDbBackedAnalysisReady(health)) {
    return {
      detail: BACKEND_UNAVAILABLE_DETAIL,
      errorType: "backend_unavailable",
    };
  }

  try {
    const report = await analyzeAddress(options.address);
    onResult(report);
    return null;
  } catch (error) {
    const detail = error instanceof Error ? error.message : fallbackDetail;
    return normalizeAnalysisError(detail, "network_error");
  }
}

export async function fetchRuntimeHealth(): Promise<RuntimeHealthData> {
  const response = await fetch(`${API_BASE}/health`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health request failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function listMcpTools(): Promise<McpToolContract[]> {
  const response = await fetch(`${API_BASE}/api/v1/mcp/tools/list`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`MCP tools request failed with HTTP ${response.status}`);
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
    const timeoutId = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

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

      let receivedFirstEvent = false;
      const receivedTerminalEvent = await consumeSseStream(
        reader,
        (eventType, parsed) => {
          receivedFirstEvent = true;
          if (eventType === "status") {
            onStatus(parsed as PipelineStatus);
          } else if (eventType === "result") {
            onResult(parsed as ZoningReportData);
            return true;
          } else if (eventType === "thinking") {
            onThinking?.(parsed as ThinkingEvent);
          } else if (eventType === "suggestions") {
            const payload = parsed as { suggestions?: string[] };
            onSuggestions?.(payload.suggestions || []);
          } else if (eventType === "error") {
            const payload = parsed as { detail?: string; error_type?: string };
            onError({
              detail: payload.detail || "Unknown error",
              errorType: (payload.error_type || "unknown") as AnalysisErrorType,
            });
            return true;
          }
          return false;
        },
        {
          readTimeoutMs: () =>
            receivedFirstEvent ? undefined : FIRST_EVENT_TIMEOUT_MS,
        },
      );

      if (!receivedTerminalEvent) {
        onError({
          detail: ANALYSIS_INCOMPLETE_DETAIL,
          errorType: "pipeline_error",
        });
      }

      return; // Success — exit retry loop
    } catch (err) {
      if (err instanceof SseProtocolError) {
        onError({
          detail: "The analysis stream sent invalid data.",
          errorType: "pipeline_error",
        });
        return;
      }

      if (isAbortError(err)) {
        onError({
          detail: STREAM_TIMEOUT_DETAIL,
          errorType: "timeout",
        });
        return;
      }

      if (isStreamStartupTimeout(err)) {
        const recoveredError = await recoverFromStreamFailure(options, onResult, NETWORK_FAILURE_DETAIL);
        if (recoveredError) {
          onError(recoveredError);
        }
        return;
      }

      // Network error — retry if we have attempts left
      if (attempt < maxRetries) {
        onRetry?.(attempt + 1);
        await new Promise((r) => setTimeout(r, 2000));
        continue;
      }

      const recoveredError = await recoverFromStreamFailure(options, onResult, NETWORK_FAILURE_DETAIL);
      if (recoveredError) {
        onError(recoveredError);
      }
      return;
    } finally {
      clearTimeout(timeoutId);
    }
  }
}

/**
 * Non-streaming analysis — simple POST, wait for full result.
 */
export async function analyzeAddress(address: string): Promise<ZoningReportData> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/api/v1/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(extractErrorMessage(err, response.status));
    }

    return response.json();
  } catch (error) {
    if (isAbortError(error)) {
      throw new Error(STREAM_TIMEOUT_DETAIL);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
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
  status?: "complete" | "error" | "blocked" | "approval_required";
  message?: string;
}

export type AgentTaskStatus = "queued" | "running" | "complete" | "attention";

export interface AgentTaskEvent {
  task_id?: string;
  task_type?: string;
  type?: string;
  title?: string;
  name?: string;
  detail?: string;
  status?: AgentTaskStatus;
  percent?: number;
  duration_ms?: number;
  url?: string | null;
  screenshot_b64?: string | null;
  citations?: string[];
}

export interface BrowserActionEvent {
  type?: string;
  action?: string;
  url?: string | null;
  selector?: string | null;
  value?: string | null;
  screenshot_b64?: string | null;
  extracted_text?: string | null;
}

export interface ReasoningEvent {
  phase?: string;
  step?: string;
  summary?: string;
  thoughts?: string[];
  alternatives?: string[];
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
  onTask?: (event: AgentTaskEvent) => void,
  onBrowserAction?: (event: BrowserActionEvent) => void,
  onReasoning?: (event: ReasoningEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  let settled = false;
  let timedOut = false;
  let idleTimeout: ReturnType<typeof setTimeout> | undefined;

  const emitError = (detail: string) => {
    if (settled) return;
    settled = true;
    onError(detail);
  };
  const emitDone = (fullContent: string) => {
    if (settled) return;
    settled = true;
    onDone(fullContent);
  };
  const refreshIdleDeadline = () => {
    if (idleTimeout) clearTimeout(idleTimeout);
    idleTimeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, CHAT_STREAM_IDLE_TIMEOUT_MS);
  };
  const abortFromCaller = () => controller.abort();

  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", abortFromCaller, { once: true });
  }
  refreshIdleDeadline();

  try {
    const response = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history,
        report_context: reportContext,
        session_id: sessionId || undefined,
      }),
      signal: controller.signal,
    });
    refreshIdleDeadline();

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Request failed" }));
      emitError(extractErrorMessage(err, response.status));
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      emitError("No response stream available. Please try again.");
      return;
    }

    const receivedTerminalEvent = await consumeSseStream(
      reader,
      (eventType, parsed) => {
        if (settled) return true;
        if (eventType === "session") {
          const payload = parsed as { session_id?: string };
          if (payload.session_id) onSession?.(payload.session_id);
        } else if (eventType === "token") {
          const payload = parsed as { content?: string };
          onToken(payload.content || "");
        } else if (eventType === "thinking") {
          onThinking?.(parsed as ThinkingEvent);
        } else if (eventType === "tool_use") {
          onToolUse?.(parsed as ToolUseEvent);
        } else if (eventType === "tool_result") {
          const payload = parsed as ToolResultEvent;
          onToolResult?.({
            tool: payload.tool,
            status: payload.status,
            message: payload.message,
          });
        } else if (eventType === "agent_task") {
          onTask?.(parsed as AgentTaskEvent);
        } else if (eventType === "browser_action") {
          onBrowserAction?.(parsed as BrowserActionEvent);
        } else if (eventType === "reasoning") {
          onReasoning?.(parsed as ReasoningEvent);
        } else if (eventType === "done") {
          const payload = parsed as { full_content?: string };
          emitDone(payload.full_content || "");
          return true;
        } else if (eventType === "error") {
          const payload = parsed as { detail?: string };
          emitError(payload.detail || "Unknown error");
          return true;
        }
        return false;
      },
      { onActivity: refreshIdleDeadline },
    );

    if (!receivedTerminalEvent) emitError(CHAT_INCOMPLETE_DETAIL);
  } catch (error) {
    if (error instanceof SseProtocolError) {
      emitError(CHAT_INVALID_DETAIL);
    } else if (timedOut) {
      emitError(CHAT_TIMEOUT_DETAIL);
    } else if (signal?.aborted || isAbortError(error)) {
      emitError(CHAT_CANCELLED_DETAIL);
    } else {
      emitError(CHAT_CONNECTION_DETAIL);
    }
  } finally {
    if (idleTimeout) clearTimeout(idleTimeout);
    signal?.removeEventListener("abort", abortFromCaller);
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
  context: Record<string, string | number | boolean>;
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

export interface GeneratedSpreadsheetResult {
  spreadsheet_id: string;
  spreadsheet_url: string;
  title: string;
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

export async function generateDocument(params: DocumentGenerateParams): Promise<Blob | GeneratedSpreadsheetResult> {
  const response = await fetch(`${API_BASE}/api/v1/documents/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Generation failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.blob();
}

// ---------------------------------------------------------------------------
// Connector Gateway — SMTP Email Outreach (Phase 5)
// ---------------------------------------------------------------------------

export interface EmailConfigParams {
  provider: "gmail" | "outlook" | "yahoo" | "custom";
  smtp_host?: string;
  smtp_port?: number;
  smtp_username: string;
  smtp_password: string;
  from_name?: string;
}

export interface EmailConfigResult {
  configured: boolean;
  provider_hint: string;
  from_name: string | null;
  smtp_username: string;
}

export interface EmailStatusResult {
  configured: boolean;
  smtp_username: string | null;
  from_name: string | null;
  provider_hint: string | null;
  daily_sends_used: number;
  daily_sends_remaining: number;
}

export interface EmailDraftParams {
  owner_name: string;
  property_address: string;
  zoning_district?: string;
  max_units?: number;
  offer_price?: number;
  sender_name?: string;
  custom_notes?: string;
}

export interface EmailDraftResult {
  subject: string;
  body_html: string;
  body_text: string;
}

export interface EmailSendParams {
  to_email: string;
  to_name?: string;
  subject: string;
  body_html: string;
  body_text?: string;
}

export interface EmailSendResult {
  sent: boolean;
  message_id: string | null;
  daily_sends_used: number;
}

function connectorHeaders(sessionId: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Session-ID": sessionId,
  };
}

export async function configureEmailConnector(
  params: EmailConfigParams,
  sessionId: string,
): Promise<EmailConfigResult> {
  const response = await fetch(`${API_BASE}/api/v1/connectors/email/configure`, {
    method: "POST",
    headers: connectorHeaders(sessionId),
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Configuration failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }
  return response.json();
}

export async function getEmailConnectorStatus(sessionId: string): Promise<EmailStatusResult> {
  const response = await fetch(`${API_BASE}/api/v1/connectors/email/status`, {
    headers: { "X-Session-ID": sessionId },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Status check failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }
  return response.json();
}

export async function testEmailConnector(sessionId: string): Promise<EmailSendResult> {
  const response = await fetch(`${API_BASE}/api/v1/connectors/email/test`, {
    method: "POST",
    headers: { "X-Session-ID": sessionId },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Test failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }
  return response.json();
}

export async function draftOutreachEmail(
  params: EmailDraftParams,
  sessionId: string,
): Promise<EmailDraftResult> {
  const response = await fetch(`${API_BASE}/api/v1/connectors/email/draft`, {
    method: "POST",
    headers: connectorHeaders(sessionId),
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Draft generation failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }
  return response.json();
}

export async function sendOutreachEmail(
  params: EmailSendParams,
  sessionId: string,
): Promise<EmailSendResult> {
  const response = await fetch(`${API_BASE}/api/v1/connectors/email/send`, {
    method: "POST",
    headers: connectorHeaders(sessionId),
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Send failed" }));
    throw new Error(extractErrorMessage(err, response.status));
  }
  return response.json();
}

export async function disconnectEmailConnector(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/connectors/email/disconnect`, {
    method: "DELETE",
    headers: { "X-Session-ID": sessionId },
  });
}

// ---------------------------------------------------------------------------
// Phase 6 — Data Center Site Selection
// ---------------------------------------------------------------------------

export interface InfraSignalData {
  name: string;
  label: string;
  score: number; // 0.0–1.0
  rating: "Excellent" | "Good" | "Fair" | "Poor";
  summary: string;
  raw_value: string;
  source: string;
  confidence: "high" | "medium" | "low";
}

export interface DataCenterParamsData {
  zoning_code: string;
  zoning_description: string;
  is_industrial_permitted: boolean | null;
  conditional_use_required: boolean | null;
  setback_front_ft: number | null;
  setback_side_ft: number | null;
  setback_rear_ft: number | null;
  max_height_ft: number | null;
  max_lot_coverage_pct: number | null;
  max_far: number | null;
  noise_limit_db: number | null;
  outdoor_equipment_allowed: boolean | null;
  min_lot_area_sqft: number | null;
  loading_docks_required: number | null;
  utility_easement_notes: string;
  source_sections: string[];
}

export interface SiteScorecardData {
  address: string;
  formatted_address: string;
  municipality: string;
  county: string;
  lat: number | null;
  lng: number | null;
  property_record: PropertyRecordData | null;
  power_signal: InfraSignalData | null;
  fiber_signal: InfraSignalData | null;
  flood_signal: InfraSignalData | null;
  seismic_signal: InfraSignalData | null;
  zoning_signal: InfraSignalData | null;
  datacenter_params: DataCenterParamsData | null;
  composite_score: number;
  composite_rating: "Excellent" | "Good" | "Fair" | "Poor" | "Disqualified" | "";
  summary: string;
  deal_breakers: string[];
  strengths: string[];
  sources: string[];
  confidence: "high" | "medium" | "low";
}

export type DatacenterPipelineSignalEvent = {
  signal: string;
  label: string;
  score: number;
  rating: string;
  summary: string;
  raw_value: string;
  source: string;
};

export async function streamDatacenterAnalysis(
  address: string,
  onStatus: (status: PipelineStatus) => void,
  onSignal: (event: DatacenterPipelineSignalEvent) => void,
  onResult: (scorecard: SiteScorecardData) => void,
  onError: (error: AnalysisError) => void,
): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 180_000); // 3 min for infra fetches

  try {
    const response = await fetch(`${API_BASE}/api/v1/analyze/datacenter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Request failed" }));
      onError({ detail: extractErrorMessage(err, response.status), errorType: "pipeline_error" });
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
            if (eventType === "status" || eventType === "cache_hit") {
              onStatus(parsed as PipelineStatus);
            } else if (eventType === "signal") {
              onSignal(parsed as DatacenterPipelineSignalEvent);
            } else if (eventType === "done") {
              onResult(parsed as SiteScorecardData);
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
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      onError({ detail: "Request timed out. Try again.", errorType: "timeout" });
      return;
    }
    onError({ detail: "Connection failed. Try again.", errorType: "network_error" });
  } finally {
    clearTimeout(timeoutId);
  }
}
