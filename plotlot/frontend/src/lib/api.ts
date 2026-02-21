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
  summary: string;
  sources: string[];
  confidence: string;
  confidence_warning?: string;
  suggested_next_steps?: string[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Stream zoning analysis with real-time pipeline progress.
 * Uses Server-Sent Events for step-by-step updates.
 */
export async function streamAnalysis(
  address: string,
  onStatus: (status: PipelineStatus) => void,
  onResult: (report: ZoningReportData) => void,
  onError: (error: string) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Request failed" }));
    onError(err.detail || `HTTP ${response.status}`);
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
          if (eventType === "status") {
            onStatus(parsed as PipelineStatus);
          } else if (eventType === "result") {
            onResult(parsed as ZoningReportData);
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
    throw new Error(err.detail || `HTTP ${response.status}`);
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
    onError(err.detail || `HTTP ${response.status}`);
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
    throw new Error(err.detail || `HTTP ${response.status}`);
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
