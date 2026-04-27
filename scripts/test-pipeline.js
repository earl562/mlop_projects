/**
 * PlotLot Pipeline Verification Script
 * 
 * Tests the full analysis pipeline by calling the backend API directly.
 * Can test against local (localhost:8000) or production backend.
 * 
 * Usage:
 *   node --env-file-if-exists=/vercel/share/.env.project scripts/test-pipeline.js
 *   
 * Environment:
 *   NEXT_PUBLIC_API_URL - Backend URL (default: http://localhost:8000)
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Test addresses for different coverage areas
const TEST_ADDRESSES = [
  { address: "7940 Plantation Blvd, Miramar, FL 33023", region: "Broward FL" },
  { address: "1200 Brickell Ave, Miami, FL 33131", region: "Miami-Dade FL" },
];

// Colors for terminal output
const colors = {
  reset: "\x1b[0m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  cyan: "\x1b[36m",
  dim: "\x1b[2m",
};

function log(msg, color = "reset") {
  console.log(`${colors[color]}${msg}${colors.reset}`);
}

function logStep(step, status, details = "") {
  const icon = status === "pass" ? "✓" : status === "fail" ? "✗" : "○";
  const color = status === "pass" ? "green" : status === "fail" ? "red" : "yellow";
  console.log(`${colors[color]}  ${icon} ${step}${colors.reset}${details ? ` ${colors.dim}${details}${colors.reset}` : ""}`);
}

async function testHealthEndpoint() {
  log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "cyan");
  log("  Testing Backend Health", "cyan");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "cyan");
  log(`  Backend URL: ${API_BASE}`, "dim");

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const response = await fetch(`${API_BASE}/health`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      logStep("Health check", "fail", `HTTP ${response.status}`);
      return { healthy: false, data: null };
    }

    const data = await response.json();
    logStep("Health check", "pass", `status: ${data.status}`);

    // Check individual health checks
    if (data.checks) {
      for (const [key, value] of Object.entries(data.checks)) {
        logStep(`  ${key}`, value === "ok" ? "pass" : "warn", String(value));
      }
    }

    // Check capabilities
    if (data.capabilities) {
      log("\n  Capabilities:", "dim");
      for (const [key, value] of Object.entries(data.capabilities)) {
        logStep(`  ${key}`, value ? "pass" : "warn", String(value));
      }
    }

    return { healthy: data.status === "healthy", data };
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    if (msg.includes("abort")) {
      logStep("Health check", "fail", "Timeout after 10s");
    } else {
      logStep("Health check", "fail", msg);
    }
    return { healthy: false, data: null };
  }
}

async function testStreamingAnalysis(address, region) {
  log(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "cyan");
  log(`  Testing Pipeline: ${region}`, "cyan");
  log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, "cyan");
  log(`  Address: ${address}`, "dim");

  const results = {
    geocode: { status: "pending", data: null },
    property: { status: "pending", data: null },
    zoning: { status: "pending", data: null },
    analysis: { status: "pending", data: null },
    calculator: { status: "pending", data: null },
    comps: { status: "pending", data: null },
    proforma: { status: "pending", data: null },
    result: { status: "pending", data: null },
  };

  const startTime = Date.now();

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000); // 2 min timeout

    const response = await fetch(`${API_BASE}/api/v1/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address,
        deal_type: "land_deal",
        skip_steps: [],
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Request failed" }));
      logStep("API request", "fail", err.detail || `HTTP ${response.status}`);
      return { success: false, results };
    }

    logStep("API request", "pass", `HTTP ${response.status}`);

    const reader = response.body?.getReader();
    if (!reader) {
      logStep("Response stream", "fail", "No stream available");
      return { success: false, results };
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
              const step = parsed.step || "unknown";
              const stepKey = step.replace(/[^a-z]/gi, "").toLowerCase();
              
              // Map common step names
              const stepMap = {
                geocoding: "geocode",
                geocode: "geocode",
                property: "property",
                propertylookup: "property",
                zoning: "zoning",
                zoningsearch: "zoning",
                analysis: "analysis",
                llmanalysis: "analysis",
                calculator: "calculator",
                densitycalculator: "calculator",
                comps: "comps",
                comparables: "comps",
                proforma: "proforma",
              };

              const mappedStep = stepMap[stepKey] || stepKey;
              if (results[mappedStep]) {
                results[mappedStep].status = parsed.complete ? "pass" : "running";
                results[mappedStep].data = parsed;
                
                const statusIcon = parsed.complete ? "pass" : "running";
                const details = parsed.message || "";
                logStep(step, statusIcon, details.slice(0, 60));
              }
            } else if (eventType === "result") {
              results.result.status = "pass";
              results.result.data = parsed;
              
              // Log key result fields
              log("\n  Pipeline Result:", "cyan");
              if (parsed.municipality) logStep("Municipality", "pass", parsed.municipality);
              if (parsed.zoning_district) logStep("Zoning", "pass", parsed.zoning_district);
              if (parsed.density_analysis?.max_units != null) {
                logStep("Max Units", "pass", String(parsed.density_analysis.max_units));
              }
              if (parsed.density_analysis?.governing_constraint) {
                logStep("Governing Constraint", "pass", parsed.density_analysis.governing_constraint);
              }
              if (parsed.confidence) logStep("Confidence", "pass", parsed.confidence);
            } else if (eventType === "error") {
              logStep("Pipeline error", "fail", parsed.detail || "Unknown error");
              return { success: false, results, error: parsed };
            } else if (eventType === "thinking") {
              // LLM thinking events - skip detailed logging
            }
          } catch {
            // Skip malformed events
          }
          eventType = "";
          eventData = "";
        }
      }
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    log(`\n  Completed in ${elapsed}s`, "dim");

    const success = results.result.status === "pass";
    return { success, results, elapsed };
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    if (msg.includes("abort")) {
      logStep("Pipeline", "fail", "Timeout after 2 minutes");
    } else {
      logStep("Pipeline", "fail", msg);
    }
    return { success: false, results };
  }
}

async function testChatEndpoint() {
  log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "cyan");
  log("  Testing Agent Chat", "cyan");
  log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "cyan");

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    const response = await fetch(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "What zoning information do you have available?",
        history: [],
        report_context: null,
      }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: "Request failed" }));
      logStep("Chat request", "fail", err.detail || `HTTP ${response.status}`);
      return { success: false };
    }

    logStep("Chat request", "pass", `HTTP ${response.status}`);

    // Read streaming response
    const reader = response.body?.getReader();
    if (!reader) {
      logStep("Chat stream", "fail", "No stream");
      return { success: false };
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let gotSession = false;
    let gotDone = false;
    let fullContent = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: session")) gotSession = true;
        if (line.startsWith("event: done")) gotDone = true;
        if (line.startsWith("data: ") && line.includes("full_content")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.full_content) fullContent = data.full_content;
          } catch {}
        }
      }
    }

    logStep("Session created", gotSession ? "pass" : "fail");
    logStep("Response completed", gotDone ? "pass" : "fail");
    if (fullContent) {
      logStep("Response length", "pass", `${fullContent.length} chars`);
    }

    return { success: gotSession && gotDone };
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    logStep("Chat", "fail", msg);
    return { success: false };
  }
}

async function main() {
  log("\n╔════════════════════════════════════════════════╗", "cyan");
  log("║         PlotLot Pipeline Verification          ║", "cyan");
  log("╚════════════════════════════════════════════════╝", "cyan");

  const summary = {
    health: false,
    pipelines: [],
    chat: false,
  };

  // 1. Health check
  const health = await testHealthEndpoint();
  summary.health = health.healthy;

  if (!health.healthy) {
    log("\n⚠ Backend not healthy. Pipeline tests may fail.", "yellow");
  }

  // 2. Test streaming analysis for each address
  for (const { address, region } of TEST_ADDRESSES) {
    const result = await testStreamingAnalysis(address, region);
    summary.pipelines.push({ region, success: result.success, elapsed: result.elapsed });
    
    // Only test one if first succeeds (to save time)
    if (result.success) break;
  }

  // 3. Test chat endpoint
  const chat = await testChatEndpoint();
  summary.chat = chat.success;

  // Final summary
  log("\n╔════════════════════════════════════════════════╗", "cyan");
  log("║                   Summary                       ║", "cyan");
  log("╚════════════════════════════════════════════════╝", "cyan");

  logStep("Backend Health", summary.health ? "pass" : "fail");
  for (const p of summary.pipelines) {
    logStep(`Pipeline (${p.region})`, p.success ? "pass" : "fail", p.elapsed ? `${p.elapsed}s` : "");
  }
  logStep("Agent Chat", summary.chat ? "pass" : "fail");

  const allPassed = summary.health && 
    summary.pipelines.some(p => p.success) && 
    summary.chat;

  log(`\n${allPassed ? "✓ All tests passed" : "✗ Some tests failed"}`, allPassed ? "green" : "red");

  process.exit(allPassed ? 0 : 1);
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
