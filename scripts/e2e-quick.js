#!/usr/bin/env node
/**
 * PlotLot Quick E2E Regression Test
 * 
 * Fast verification of critical paths with reduced test set.
 * For full regression, use e2e-regression.js
 * 
 * Usage: NEXT_PUBLIC_API_URL="https://plotlot-api.onrender.com" node scripts/e2e-quick.js
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
  dim: "\x1b[2m",
  bold: "\x1b[1m",
};

// Quick test cases - one per category
const QUICK_TESTS = [
  // Happy paths
  {
    id: "happy_broward",
    name: "Happy: Broward FL Lookup",
    type: "pipeline",
    address: "7940 Plantation Blvd, Miramar, FL 33023",
    expectSuccess: true,
    validate: (r) => r.municipality?.includes("Miramar") && r.zoning_district,
  },
  {
    id: "happy_miami",
    name: "Happy: Miami-Dade FL Lookup", 
    type: "pipeline",
    address: "1234 SW 42nd Ave, Miami, FL 33134",
    expectSuccess: true,
    validate: (r) => r.county?.includes("Miami-Dade"),
  },
  // Unhappy paths
  {
    id: "unhappy_gibberish",
    name: "Unhappy: Gibberish Address",
    type: "pipeline",
    address: "asdfghjkl qwerty 12345",
    expectSuccess: false,
    expectError: ["bad_address", "geocoding_failed", "low_accuracy"],
  },
  {
    id: "unhappy_empty",
    name: "Unhappy: Empty Address",
    type: "pipeline",
    address: "",
    expectSuccess: false,
    expectError: ["bad_address", "pipeline_error"],
  },
  // Agent chat
  {
    id: "agent_simple",
    name: "Agent: Simple Question",
    type: "chat",
    message: "What zoning types allow multifamily?",
    expectSuccess: true,
  },
];

async function fetchWithTimeout(url, options, timeout = 120000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeoutId);
    return res;
  } catch (e) {
    clearTimeout(timeoutId);
    throw e;
  }
}

async function testPipeline(test) {
  const start = Date.now();
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/v1/analyze/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: test.address, deal_type: "land_deal", skip_steps: [] }),
    }, 180000);

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return {
        pass: !test.expectSuccess,
        reason: `HTTP ${res.status}: ${err.detail || "unknown"}`,
        elapsed: ((Date.now() - start) / 1000).toFixed(1),
      };
    }

    // Parse SSE
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", eventType = "", eventData = "";
    let result = null, error = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        else if (line.startsWith("data: ")) eventData = line.slice(6).trim();
        else if (line === "" && eventType && eventData) {
          try {
            const p = JSON.parse(eventData);
            if (eventType === "result") result = p;
            if (eventType === "error") error = p;
          } catch {}
          eventType = eventData = "";
        }
      }
    }

    const elapsed = ((Date.now() - start) / 1000).toFixed(1);

    if (error) {
      if (!test.expectSuccess && test.expectError?.includes(error.errorType)) {
        return { pass: true, reason: `Expected error: ${error.errorType}`, elapsed };
      }
      return { pass: !test.expectSuccess, reason: `Error: ${error.detail}`, elapsed };
    }

    if (result) {
      if (test.expectSuccess) {
        const valid = !test.validate || test.validate(result);
        return {
          pass: valid,
          reason: valid ? `Success: ${result.municipality} | ${result.zoning_district}` : "Validation failed",
          elapsed,
          data: { municipality: result.municipality, zoning: result.zoning_district, maxUnits: result.density_analysis?.max_units },
        };
      }
      // For tests expecting failure - check if we got a low-confidence or garbage result
      const confidence = result.confidence || "unknown";
      const hasWarning = result.confidence_warning || result.summary?.includes("could not");
      if (confidence === "low" || hasWarning) {
        return { 
          pass: true, 
          reason: `Low confidence result (acceptable): ${result.municipality || "unknown"} | confidence: ${confidence}`, 
          elapsed,
          note: "Pipeline returned result but with low confidence - acceptable for error case"
        };
      }
      return { 
        pass: false, 
        reason: `Got result but expected error. Municipality: ${result.municipality}, Confidence: ${confidence}`, 
        elapsed,
        data: { municipality: result.municipality, confidence, address: result.address }
      };
    }

    return { pass: false, reason: "No result or error", elapsed };
  } catch (e) {
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    if (!test.expectSuccess) return { pass: true, reason: `Expected failure: ${e.message}`, elapsed };
    return { pass: false, reason: e.message, elapsed };
  }
}

async function testChat(test) {
  const start = Date.now();
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: test.message, history: [], report_context: null }),
    }, 60000);

    if (!res.ok) {
      return { pass: false, reason: `HTTP ${res.status}`, elapsed: ((Date.now() - start) / 1000).toFixed(1) };
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", content = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      let eventType = "", eventData = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) eventType = line.slice(7).trim();
        else if (line.startsWith("data: ")) eventData = line.slice(6).trim();
        else if (line === "" && eventType && eventData) {
          try {
            const p = JSON.parse(eventData);
            if (eventType === "token") content += p.content;
            if (eventType === "done") content = p.full_content || content;
          } catch {}
          eventType = eventData = "";
        }
      }
    }

    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    return {
      pass: content.length > 20,
      reason: content.length > 20 ? `Response: ${content.length} chars` : "Response too short",
      elapsed,
    };
  } catch (e) {
    return { pass: false, reason: e.message, elapsed: ((Date.now() - start) / 1000).toFixed(1) };
  }
}

async function main() {
  console.log(`\n${colors.bold}PlotLot Quick E2E Tests${colors.reset}`);
  console.log(`${colors.dim}API: ${API_BASE}${colors.reset}`);
  console.log(`${colors.dim}Time: ${new Date().toISOString()}${colors.reset}\n`);

  // Health check first
  console.log(`${colors.cyan}[TEST]${colors.reset} Health Check`);
  try {
    const health = await fetchWithTimeout(`${API_BASE}/health`, {}, 15000);
    if (health.ok) {
      const data = await health.json();
      console.log(`${colors.green}[PASS]${colors.reset} Backend: ${data.status}\n`);
    } else {
      console.log(`${colors.yellow}[WARN]${colors.reset} Backend returned ${health.status}\n`);
    }
  } catch (e) {
    console.log(`${colors.yellow}[WARN]${colors.reset} Health check failed: ${e.message}\n`);
  }

  const results = [];

  for (const test of QUICK_TESTS) {
    console.log(`${colors.cyan}[TEST]${colors.reset} ${test.name}`);
    
    let result;
    if (test.type === "pipeline") {
      result = await testPipeline(test);
    } else if (test.type === "chat") {
      result = await testChat(test);
    }

    results.push({ ...test, ...result });

    if (result.pass) {
      console.log(`${colors.green}[PASS]${colors.reset} ${result.reason} (${result.elapsed}s)`);
    } else {
      console.log(`${colors.red}[FAIL]${colors.reset} ${result.reason} (${result.elapsed}s)`);
    }
    console.log();
  }

  // Summary
  const passed = results.filter(r => r.pass).length;
  const failed = results.filter(r => !r.pass).length;
  
  console.log(`${colors.bold}${"=".repeat(50)}${colors.reset}`);
  console.log(`${colors.bold}SUMMARY${colors.reset}`);
  console.log(`  Total: ${results.length}`);
  console.log(`  ${colors.green}Passed: ${passed}${colors.reset}`);
  console.log(`  ${colors.red}Failed: ${failed}${colors.reset}`);
  console.log(`  Rate: ${((passed / results.length) * 100).toFixed(0)}%`);
  console.log(`${colors.bold}${"=".repeat(50)}${colors.reset}\n`);

  process.exit(failed > 0 ? 1 : 0);
}

main().catch(e => {
  console.error(`${colors.red}Fatal: ${e.message}${colors.reset}`);
  process.exit(1);
});
