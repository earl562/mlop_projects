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
const NETWORK_FAILURE_DETAIL = "Connection failed. The server may be starting up — try again in a moment.";
const BACKEND_UNAVAILABLE_DETAIL =
  "Analysis is temporarily unavailable because the data backend is offline. Please try again shortly.";
const STREAM_TIMEOUT_DETAIL =
  "Request timed out after 2 minutes. The server may be starting up — try again.";

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isStreamStartupTimeout(error: unknown): boolean {
  return error instanceof Error && error.message === "STREAM_FIRST_EVENT_TIMEOUT";
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

      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "";
      let eventData = "";
      let receivedFirstEvent = false;
      let receivedTerminalEvent = false;

      while (true) {
        const readResult = receivedFirstEvent
          ? reader.read()
          : Promise.race([
              reader.read(),
              new Promise<never>((_, reject) => {
                setTimeout(() => reject(new Error("STREAM_FIRST_EVENT_TIMEOUT")), FIRST_EVENT_TIMEOUT_MS);
              }),
            ]);
        const { done, value } = await readResult;
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
              receivedFirstEvent = true;
              if (eventType === "status") {
                onStatus(parsed as PipelineStatus);
              } else if (eventType === "result") {
                receivedTerminalEvent = true;
                onResult(parsed as ZoningReportData);
              } else if (eventType === "thinking") {
                onThinking?.(parsed as ThinkingEvent);
              } else if (eventType === "suggestions") {
                onSuggestions?.(parsed.suggestions || []);
              } else if (eventType === "error") {
                receivedTerminalEvent = true;
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

      if (!receivedTerminalEvent) {
        const recoveredError = await recoverFromStreamFailure(
          options,
          onResult,
          receivedFirstEvent
            ? "The analysis stream ended before a final result was returned."
            : NETWORK_FAILURE_DETAIL,
        );
        if (recoveredError) {
          onError(recoveredError);
        }
      }

      return; // Success — exit retry loop
    } catch (err) {
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
  onToolResult?: (tool: string) => void,
  onThinking?: (event: ThinkingEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history,
      report_context: reportContext,
      session_id: sessionId || undefined,
    }),
  });

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
          if (eventType === "session") {
            onSession?.(parsed.session_id);
          } else if (eventType === "token") {
            onToken(parsed.content);
          } else if (eventType === "thinking") {
            onThinking?.(parsed as ThinkingEvent);
          } else if (eventType === "tool_use") {
            onToolUse?.(parsed as ToolUseEvent);
          } else if (eventType === "tool_result") {
            onToolResult?.(parsed.tool);
          } else if (eventType === "done") {
            onDone(parsed.full_content);
          } else if (eventType === "error") {
            onError(parsed.detail || "Unknown error");
          }
        } catch {
          // Skip malformed events
        }
        eventType = "";
        eventData = "";
      }
    }
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
// Acquisition — Deals, Pipeline, Outreach
// ---------------------------------------------------------------------------

export interface DealData {
  id: string;
  workspace_id: string;
  project_id: string;
  site_id?: string | null;
  title: string;
  description?: string;
  deal_type: string;
  property_address: string;
  owner_name?: string;
  owner_email?: string;
  owner_phone?: string;
  asking_price?: number;
  offer_price?: number;
  feasibility_score?: number;
  stage: string;
  status: string;
  is_deleted: boolean;
  assigned_to_user_id?: string;
  source?: string;
  stage_entered_at?: string;
  created_at?: string;
  updated_at?: string;
  outreach_activities?: OutreachActivityData[];
  stage_history?: StageHistoryData[];
}

export interface StageHistoryData {
  id: string;
  deal_id: string;
  from_stage: string;
  to_stage: string;
  transitioned_at?: string;
  transitioned_by_user_id?: string;
  trigger_type: string;
}

export interface OutreachActivityData {
  id: string;
  deal_id: string;
  activity_type: "email" | "call" | "meeting";
  direction?: string;
  subject?: string;
  body?: string;
  call_outcome?: string;
  call_duration_seconds?: number;
  sentiment?: string;
  to_address?: string;
  to_name?: string;
  status?: string;
  created_at?: string;
}

export interface PipelineMetricsData {
  total_deals: number;
  stage_distribution: Record<string, number>;
  total_pipeline_value: number;
}

export interface ConnectorData {
  id: string;
  workspace_id: string;
  provider: string;
  auth_type: string;
  scopes: string[];
  status: string;
  created_at?: string;
}

export async function listDeals(workspaceId?: string): Promise<DealData[]> {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  const response = await fetch(`${API_BASE}/api/v1/deals?${params.toString()}`);
  if (!response.ok) throw new Error("Failed to load deals");
  const data = await response.json();
  return data.items || [];
}

export async function createDeal(payload: Partial<DealData>): Promise<DealData> {
  const response = await fetch(`${API_BASE}/api/v1/deals`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail || "Failed to create deal");
  }
  return response.json();
}

export async function getDeal(dealId: string): Promise<DealData> {
  const response = await fetch(`${API_BASE}/api/v1/deals/${dealId}`);
  if (!response.ok) throw new Error("Failed to load deal");
  return response.json();
}

export async function updateDeal(dealId: string, payload: Partial<DealData>): Promise<DealData> {
  const response = await fetch(`${API_BASE}/api/v1/deals/${dealId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("Failed to update deal");
  return response.json();
}

export async function deleteDeal(dealId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/deals/${dealId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed to delete deal");
}

export async function transitionDeal(
  dealId: string,
  toStage: string,
  userId?: string,
): Promise<DealData> {
  const response = await fetch(`${API_BASE}/api/v1/deals/${dealId}/transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_stage: toStage, user_id: userId }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Transition failed" }));
    throw new Error(err.detail || "Failed to transition deal");
  }
  return response.json();
}

export async function getPipelineMetrics(workspaceId?: string): Promise<PipelineMetricsData> {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  const response = await fetch(`${API_BASE}/api/v1/deals/metrics?${params.toString()}`);
  if (!response.ok) throw new Error("Failed to load metrics");
  return response.json();
}

export async function logOutreach(
  dealId: string,
  payload: Partial<OutreachActivityData>,
): Promise<OutreachActivityData> {
  const response = await fetch(`${API_BASE}/api/v1/deals/${dealId}/outreach`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Log outreach failed" }));
    throw new Error(err.detail || "Failed to log outreach");
  }
  return response.json();
}

export async function getOutreachMetrics(): Promise<{ total_activities: number; emails: number; calls: number; meetings: number; interested_calls: number }> {
  const response = await fetch(`${API_BASE}/api/v1/outreach/metrics`);
  if (!response.ok) throw new Error("Failed to load outreach metrics");
  return response.json();
}

export async function listConnectors(workspaceId?: string): Promise<ConnectorData[]> {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  const response = await fetch(`${API_BASE}/api/v1/connectors?${params.toString()}`);
  if (!response.ok) throw new Error("Failed to load connectors");
  const data = await response.json();
  return data.items || [];
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
