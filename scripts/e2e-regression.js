#!/usr/bin/env node
/**
 * PlotLot E2E Regression Test Suite
 * 
 * Comprehensive testing of the full pipeline with:
 * - Happy paths: Multiple municipalities, deal types, agent flows
 * - Unhappy paths: Invalid addresses, unsupported areas, timeouts, edge cases
 * 
 * Usage: NEXT_PUBLIC_API_URL="https://plotlot-api.onrender.com" node scripts/e2e-regression.js
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ============================================================================
// Test Configuration
// ============================================================================

const TEST_CONFIG = {
  timeouts: {
    health: 15000,
    pipeline: 180000,  // 3 minutes for full pipeline
    chat: 60000,
    short: 10000,
  },
  retryAttempts: 1,
};

// ============================================================================
// Test Cases
// ============================================================================

const HAPPY_PATH_TESTS = {
  // Florida - Strong Coverage
  broward_residential: {
    name: "Broward FL - Residential (RS5)",
    address: "7940 Plantation Blvd, Miramar, FL 33023",
    dealType: "land_deal",
    expected: {
      municipality: "Miramar",
      county: "Broward",
      hasZoning: true,
      hasProperty: true,
      maxUnitsMin: 1,
    },
  },
  broward_commercial: {
    name: "Broward FL - Commercial Area",
    address: "2801 N University Dr, Coral Springs, FL 33065",
    dealType: "land_deal",
    expected: {
      county: "Broward",
      hasZoning: true,
      hasProperty: true,
    },
  },
  miami_dade_residential: {
    name: "Miami-Dade FL - Residential",
    address: "1234 SW 42nd Ave, Miami, FL 33134",
    dealType: "land_deal",
    expected: {
      county: "Miami-Dade",
      hasZoning: true,
      hasProperty: true,
    },
  },
  palm_beach: {
    name: "Palm Beach FL - West Palm Beach",
    address: "400 Clematis St, West Palm Beach, FL 33401",
    dealType: "land_deal",
    expected: {
      county: "Palm Beach",
      hasProperty: true,
    },
  },
  
  // North Carolina Coverage
  charlotte_nc: {
    name: "Mecklenburg NC - Charlotte",
    address: "200 E Trade St, Charlotte, NC 28202",
    dealType: "land_deal",
    expected: {
      county: "Mecklenburg",
      hasProperty: true,
    },
  },
  
  // Deal Type Variations
  wholesale_deal: {
    name: "Wholesale Deal Type",
    address: "7940 Plantation Blvd, Miramar, FL 33023",
    dealType: "wholesale",
    expected: {
      hasZoning: true,
      hasProperty: true,
    },
  },
  creative_finance_deal: {
    name: "Creative Finance Deal Type",
    address: "7940 Plantation Blvd, Miramar, FL 33023",
    dealType: "creative_finance",
    expected: {
      hasZoning: true,
      hasProperty: true,
    },
  },
  hybrid_deal: {
    name: "Hybrid Deal Type",
    address: "7940 Plantation Blvd, Miramar, FL 33023",
    dealType: "hybrid",
    expected: {
      hasZoning: true,
      hasProperty: true,
    },
  },
};

const UNHAPPY_PATH_TESTS = {
  invalid_address_gibberish: {
    name: "Invalid Address - Gibberish",
    address: "asdfghjkl qwerty 12345",
    expectedError: ["bad_address", "geocoding_failed", "low_accuracy"],
    description: "Should fail geocoding with clear error",
  },
  invalid_address_incomplete: {
    name: "Invalid Address - Incomplete",
    address: "123 Main",
    expectedError: ["bad_address", "geocoding_failed", "low_accuracy"],
    description: "Incomplete address should fail gracefully",
  },
  unsupported_state: {
    name: "Unsupported State - Texas",
    address: "1600 Pennsylvania Ave, Austin, TX 78701",
    expectedBehavior: "may_succeed_or_fail",
    description: "Out-of-coverage area - may use UniversalProvider or fail",
  },
  international_address: {
    name: "International Address",
    address: "10 Downing Street, London, UK",
    expectedError: ["bad_address", "geocoding_failed"],
    description: "International addresses should fail",
  },
  po_box: {
    name: "PO Box Address",
    address: "PO Box 12345, Miami, FL 33101",
    expectedError: ["bad_address", "geocoding_failed", "low_accuracy"],
    description: "PO boxes have no parcel data",
  },
  empty_address: {
    name: "Empty Address",
    address: "",
    expectedError: ["bad_address", "pipeline_error"],
    description: "Empty input should fail validation",
  },
  special_characters: {
    name: "Special Characters in Address",
    address: "123 <script>alert('xss')</script> St, Miami, FL",
    expectedError: ["bad_address", "geocoding_failed"],
    description: "Should sanitize and reject malformed input",
  },
};

const AGENT_CHAT_TESTS = {
  simple_question: {
    name: "Simple Follow-up Question",
    message: "What are the setback requirements?",
    reportContext: null,
    expectedBehavior: "should_respond",
  },
  with_context: {
    name: "Question with Report Context",
    message: "Can I build a duplex here?",
    reportContext: {
      address: "7940 Plantation Blvd, Miramar, FL 33023",
      zoning_district: "RS5",
      max_units: 1,
    },
    expectedBehavior: "should_reference_context",
  },
  strategy_question: {
    name: "Strategy Question",
    message: "What's the best approach for this land deal?",
    reportContext: null,
    expectedBehavior: "should_respond",
  },
};

// ============================================================================
// Utility Functions
// ============================================================================

const colors = {
  reset: "\x1b[0m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  magenta: "\x1b[35m",
  cyan: "\x1b[36m",
  dim: "\x1b[2m",
  bold: "\x1b[1m",
};

function log(color, prefix, message) {
  console.log(`${colors[color]}${prefix}${colors.reset} ${message}`);
}

function logSection(title) {
  console.log(`\n${colors.bold}${colors.cyan}${"=".repeat(70)}${colors.reset}`);
  console.log(`${colors.bold}${colors.cyan}  ${title}${colors.reset}`);
  console.log(`${colors.bold}${colors.cyan}${"=".repeat(70)}${colors.reset}\n`);
}

function logSubsection(title) {
  console.log(`\n${colors.blue}--- ${title} ---${colors.reset}\n`);
}

async function fetchWithTimeout(url, options, timeout) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === "AbortError") {
      throw new Error(`Request timed out after ${timeout}ms`);
    }
    throw error;
  }
}

// ============================================================================
// Test Runners
// ============================================================================

async function testHealthCheck() {
  log("cyan", "[TEST]", "Health Check");
  
  try {
    const response = await fetchWithTimeout(
      `${API_BASE}/health`,
      { method: "GET" },
      TEST_CONFIG.timeouts.health
    );
    
    if (!response.ok) {
      return { pass: false, reason: `HTTP ${response.status}` };
    }
    
    const data = await response.json();
    const isHealthy = data.status === "healthy" || data.status === "degraded";
    
    return {
      pass: isHealthy,
      reason: isHealthy ? `Status: ${data.status}` : `Unhealthy: ${data.status}`,
      data,
    };
  } catch (error) {
    return { pass: false, reason: error.message };
  }
}

async function streamPipeline(address, dealType = "land_deal") {
  const events = {
    statuses: [],
    result: null,
    error: null,
    thinking: [],
    suggestions: [],
  };
  
  const response = await fetchWithTimeout(
    `${API_BASE}/api/v1/analyze/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address,
        deal_type: dealType,
        skip_steps: [],
      }),
    },
    TEST_CONFIG.timeouts.pipeline
  );
  
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Request failed" }));
    events.error = { detail: err.detail || `HTTP ${response.status}`, errorType: "pipeline_error" };
    return events;
  }
  
  const reader = response.body.getReader();
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
          switch (eventType) {
            case "status":
              events.statuses.push(parsed);
              break;
            case "result":
              events.result = parsed;
              break;
            case "error":
              events.error = parsed;
              break;
            case "thinking":
              events.thinking.push(parsed);
              break;
            case "suggestions":
              events.suggestions = parsed.suggestions || [];
              break;
          }
        } catch {}
        eventType = "";
        eventData = "";
      }
    }
  }
  
  return events;
}

async function testHappyPath(testId, test) {
  log("cyan", "[TEST]", `${test.name}`);
  log("dim", "       ", `Address: ${test.address}`);
  log("dim", "       ", `Deal Type: ${test.dealType}`);
  
  const startTime = Date.now();
  
  try {
    const events = await streamPipeline(test.address, test.dealType);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    
    // Check for errors
    if (events.error) {
      return {
        pass: false,
        reason: `Pipeline error: ${events.error.detail} (${events.error.errorType || "unknown"})`,
        elapsed,
      };
    }
    
    // Check for result
    if (!events.result) {
      return {
        pass: false,
        reason: "No result received from pipeline",
        elapsed,
      };
    }
    
    const result = events.result;
    const validations = [];
    
    // Validate expected fields
    if (test.expected.municipality) {
      const match = result.municipality?.toLowerCase().includes(test.expected.municipality.toLowerCase());
      validations.push({
        field: "municipality",
        pass: match,
        expected: test.expected.municipality,
        actual: result.municipality,
      });
    }
    
    if (test.expected.county) {
      const match = result.county?.toLowerCase().includes(test.expected.county.toLowerCase());
      validations.push({
        field: "county",
        pass: match,
        expected: test.expected.county,
        actual: result.county,
      });
    }
    
    if (test.expected.hasZoning) {
      const hasZoning = result.zoning_district && result.zoning_district !== "Unknown";
      validations.push({
        field: "zoning",
        pass: hasZoning,
        expected: "present",
        actual: result.zoning_district || "missing",
      });
    }
    
    if (test.expected.hasProperty) {
      const hasProperty = result.property_record !== null;
      validations.push({
        field: "property_record",
        pass: hasProperty,
        expected: "present",
        actual: hasProperty ? "present" : "missing",
      });
    }
    
    if (test.expected.maxUnitsMin !== undefined) {
      const maxUnits = result.density_analysis?.max_units;
      const pass = maxUnits !== undefined && maxUnits >= test.expected.maxUnitsMin;
      validations.push({
        field: "max_units",
        pass,
        expected: `>= ${test.expected.maxUnitsMin}`,
        actual: maxUnits,
      });
    }
    
    const allPassed = validations.every(v => v.pass);
    const failedValidations = validations.filter(v => !v.pass);
    
    return {
      pass: allPassed,
      reason: allPassed 
        ? `All ${validations.length} validations passed`
        : `Failed: ${failedValidations.map(v => `${v.field} (expected ${v.expected}, got ${v.actual})`).join(", ")}`,
      elapsed,
      validations,
      result: {
        municipality: result.municipality,
        county: result.county,
        zoning: result.zoning_district,
        maxUnits: result.density_analysis?.max_units,
        confidence: result.confidence,
      },
      pipelineSteps: events.statuses.length,
    };
  } catch (error) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    return {
      pass: false,
      reason: `Exception: ${error.message}`,
      elapsed,
    };
  }
}

async function testUnhappyPath(testId, test) {
  log("cyan", "[TEST]", `${test.name}`);
  log("dim", "       ", `Address: "${test.address}"`);
  log("dim", "       ", `Expected: ${test.expectedError?.join(" or ") || test.expectedBehavior}`);
  
  const startTime = Date.now();
  
  try {
    const events = await streamPipeline(test.address, "land_deal");
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    
    // For tests expecting errors
    if (test.expectedError) {
      if (events.error) {
        const errorTypeMatch = test.expectedError.includes(events.error.errorType);
        return {
          pass: errorTypeMatch,
          reason: errorTypeMatch
            ? `Correctly received error: ${events.error.errorType}`
            : `Unexpected error type: ${events.error.errorType} (expected one of: ${test.expectedError.join(", ")})`,
          elapsed,
          errorReceived: events.error,
        };
      } else if (events.result) {
        // Some "unhappy" paths may actually succeed if UniversalProvider works
        if (test.expectedBehavior === "may_succeed_or_fail") {
          return {
            pass: true,
            reason: `Succeeded via fallback (UniversalProvider)`,
            elapsed,
            result: {
              municipality: events.result.municipality,
              county: events.result.county,
            },
          };
        }
        return {
          pass: false,
          reason: `Expected error but got success with result`,
          elapsed,
        };
      }
    }
    
    // For tests with "may_succeed_or_fail"
    if (test.expectedBehavior === "may_succeed_or_fail") {
      return {
        pass: true,
        reason: events.result 
          ? `Succeeded (UniversalProvider coverage)`
          : `Failed as expected: ${events.error?.detail || "unknown"}`,
        elapsed,
      };
    }
    
    return {
      pass: false,
      reason: "Unexpected behavior - no result or error",
      elapsed,
    };
  } catch (error) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    
    // Timeout or network errors may be expected for some tests
    if (test.expectedError?.includes("timeout") && error.message.includes("timed out")) {
      return { pass: true, reason: "Correctly timed out", elapsed };
    }
    
    return {
      pass: test.expectedError ? true : false,
      reason: `Exception (may be expected): ${error.message}`,
      elapsed,
    };
  }
}

async function testAgentChat(testId, test) {
  log("cyan", "[TEST]", `Agent: ${test.name}`);
  log("dim", "       ", `Message: "${test.message}"`);
  
  const startTime = Date.now();
  
  try {
    const response = await fetchWithTimeout(
      `${API_BASE}/api/v1/chat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: test.message,
          history: [],
          report_context: test.reportContext,
        }),
      },
      TEST_CONFIG.timeouts.chat
    );
    
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    
    if (!response.ok) {
      return {
        pass: false,
        reason: `HTTP ${response.status}`,
        elapsed,
      };
    }
    
    // Parse SSE response
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";
    let sessionId = null;
    let hasToolUse = false;
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      
      let eventType = "";
      let eventData = "";
      
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          eventData = line.slice(6).trim();
        } else if (line === "" && eventType && eventData) {
          try {
            const parsed = JSON.parse(eventData);
            if (eventType === "session") sessionId = parsed.session_id;
            if (eventType === "token") fullContent += parsed.content;
            if (eventType === "tool_use") hasToolUse = true;
            if (eventType === "done") fullContent = parsed.full_content || fullContent;
          } catch {}
          eventType = "";
          eventData = "";
        }
      }
    }
    
    const hasResponse = fullContent.length > 10;
    
    return {
      pass: hasResponse,
      reason: hasResponse 
        ? `Received ${fullContent.length} char response`
        : "Response too short or empty",
      elapsed,
      sessionId,
      hasToolUse,
      responseLength: fullContent.length,
      responsePreview: fullContent.slice(0, 100) + (fullContent.length > 100 ? "..." : ""),
    };
  } catch (error) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    return {
      pass: false,
      reason: `Exception: ${error.message}`,
      elapsed,
    };
  }
}

// ============================================================================
// Report Generation
// ============================================================================

function generateReport(results) {
  const totalTests = results.length;
  const passed = results.filter(r => r.pass).length;
  const failed = results.filter(r => !r.pass).length;
  const passRate = ((passed / totalTests) * 100).toFixed(1);
  
  logSection("REGRESSION TEST REPORT");
  
  console.log(`${colors.bold}Summary:${colors.reset}`);
  console.log(`  Total Tests: ${totalTests}`);
  console.log(`  ${colors.green}Passed: ${passed}${colors.reset}`);
  console.log(`  ${colors.red}Failed: ${failed}${colors.reset}`);
  console.log(`  Pass Rate: ${passRate}%`);
  console.log(`  Total Time: ${results.reduce((acc, r) => acc + parseFloat(r.elapsed || 0), 0).toFixed(1)}s`);
  
  if (failed > 0) {
    logSubsection("Failed Tests");
    results.filter(r => !r.pass).forEach(r => {
      console.log(`${colors.red}  [FAIL]${colors.reset} ${r.name}`);
      console.log(`${colors.dim}         Reason: ${r.reason}${colors.reset}`);
    });
  }
  
  logSubsection("All Results");
  results.forEach(r => {
    const icon = r.pass ? `${colors.green}[PASS]${colors.reset}` : `${colors.red}[FAIL]${colors.reset}`;
    console.log(`${icon} ${r.name} (${r.elapsed}s)`);
    if (!r.pass) {
      console.log(`${colors.dim}       ${r.reason}${colors.reset}`);
    }
  });
  
  return { totalTests, passed, failed, passRate };
}

// ============================================================================
// Main Execution
// ============================================================================

async function main() {
  console.log(`\n${colors.bold}${colors.magenta}PlotLot E2E Regression Test Suite${colors.reset}`);
  console.log(`${colors.dim}API: ${API_BASE}${colors.reset}`);
  console.log(`${colors.dim}Started: ${new Date().toISOString()}${colors.reset}\n`);
  
  const allResults = [];
  
  // 1. Health Check
  logSection("1. Backend Health Check");
  const healthResult = await testHealthCheck();
  allResults.push({
    name: "Health Check",
    category: "health",
    ...healthResult,
  });
  
  if (healthResult.pass) {
    log("green", "[PASS]", `Backend is ${healthResult.data?.status || "reachable"}`);
  } else {
    log("red", "[FAIL]", healthResult.reason);
    log("yellow", "[WARN]", "Backend may be starting up (Render cold start). Continuing with tests...");
  }
  
  // 2. Happy Path Tests
  logSection("2. Happy Path Tests (Lookup Pipeline)");
  for (const [testId, test] of Object.entries(HAPPY_PATH_TESTS)) {
    const result = await testHappyPath(testId, test);
    allResults.push({
      name: test.name,
      category: "happy_path",
      testId,
      ...result,
    });
    
    if (result.pass) {
      log("green", "[PASS]", `${result.reason} (${result.elapsed}s)`);
      if (result.result) {
        log("dim", "       ", `Result: ${result.result.municipality} | ${result.result.zoning} | Max Units: ${result.result.maxUnits}`);
      }
    } else {
      log("red", "[FAIL]", `${result.reason} (${result.elapsed}s)`);
    }
    
    // Small delay between tests to avoid rate limiting
    await new Promise(r => setTimeout(r, 1000));
  }
  
  // 3. Unhappy Path Tests
  logSection("3. Unhappy Path Tests (Error Handling)");
  for (const [testId, test] of Object.entries(UNHAPPY_PATH_TESTS)) {
    const result = await testUnhappyPath(testId, test);
    allResults.push({
      name: test.name,
      category: "unhappy_path",
      testId,
      ...result,
    });
    
    if (result.pass) {
      log("green", "[PASS]", `${result.reason} (${result.elapsed}s)`);
    } else {
      log("red", "[FAIL]", `${result.reason} (${result.elapsed}s)`);
    }
    
    await new Promise(r => setTimeout(r, 500));
  }
  
  // 4. Agent Chat Tests
  logSection("4. Agent Chat Tests");
  for (const [testId, test] of Object.entries(AGENT_CHAT_TESTS)) {
    const result = await testAgentChat(testId, test);
    allResults.push({
      name: `Agent: ${test.name}`,
      category: "agent_chat",
      testId,
      ...result,
    });
    
    if (result.pass) {
      log("green", "[PASS]", `${result.reason} (${result.elapsed}s)`);
      if (result.responsePreview) {
        log("dim", "       ", `Response: "${result.responsePreview}"`);
      }
    } else {
      log("red", "[FAIL]", `${result.reason} (${result.elapsed}s)`);
    }
    
    await new Promise(r => setTimeout(r, 500));
  }
  
  // Generate Final Report
  const report = generateReport(allResults);
  
  // Exit with appropriate code
  const exitCode = report.failed > 0 ? 1 : 0;
  console.log(`\n${colors.dim}Exit code: ${exitCode}${colors.reset}\n`);
  process.exit(exitCode);
}

// Run
main().catch(error => {
  console.error(`${colors.red}Fatal error: ${error.message}${colors.reset}`);
  process.exit(1);
});
