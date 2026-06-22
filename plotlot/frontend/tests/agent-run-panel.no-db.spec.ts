import {
  expect,
  gotoHome,
  runLookupFlow,
  stubAnalyzeStream,
  test,
  waitForReport,
} from "./helpers";
import { reportWithLookupSnapshot, visualViewports } from "./fixtures/agentRunPanel";
import {
  goldenBatchPayload,
  noHistoryReleaseGatePayload,
  passedReleaseGatePayload,
} from "./fixtures/agentRunPanelReleaseGate";
import { agentRunEval, agentRunTrace } from "./fixtures/agentRunTrace";

test.describe("Agent run panel no-db flow", () => {
  test("evaluates a snapshot-backed report through the browser UI", async ({ page }, testInfo) => {
    let goldenRunRecorded = false;
    await page.route("**/api/v1/lookup-snapshots/evals/batch/release-gate**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          goldenRunRecorded ? passedReleaseGatePayload : noHistoryReleaseGatePayload,
        ),
      });
    });

    await page.route("**/api/v1/lookup-snapshots/evals/batch/golden", async (route) => {
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toMatchObject({
        suite: "lookup_correctness",
        snapshots: [
          {
            snapshot_id: "lookup_e2e_agent_snapshot",
            address: reportWithLookupSnapshot.address,
          },
        ],
      });
      goldenRunRecorded = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(goldenBatchPayload),
      });
    });

    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Resolving address", complete: true },
        { step: "zoning", message: "Verifying zoning district", complete: true },
      ],
      result: reportWithLookupSnapshot,
    });

    await page.route("**/api/v1/agent-runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: "run_e2e_agent",
          lookup_snapshot_id: "lookup_e2e_agent_snapshot",
          workspace_id: "frontend_workspace",
          status: "requires_review",
          evidence_ids: ["evidence-parcel-e2e", "evidence-zoning-e2e"],
          warnings: [],
          ready_for_synthesis: false,
        }),
      });
    });

    await page.route("**/api/v1/agent-runs/run_e2e_agent/evals?workspace_id=frontend_workspace", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(agentRunEval),
      });
    });

    await page.route(
      "**/api/v1/agent-runs/run_e2e_agent/improvement-summary?workspace_id=frontend_workspace",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            current: agentRunEval,
            previous: null,
            baseline_status: "missing",
            improvement_status: "no_baseline",
            release_blocked: false,
            deltas: {},
            improved_metric_keys: [],
            regressed_metric_keys: [],
          }),
        });
      },
    );

    await page.route("**/api/v1/agent-runs/run_e2e_agent/trace?workspace_id=frontend_workspace", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(agentRunTrace),
      });
    });

    await gotoHome(page);
    await runLookupFlow(page, reportWithLookupSnapshot.address);
    await waitForReport(page);

    const panel = page.getByTestId("agent-run-panel");
    await expect(panel).toBeVisible();
    await expect(page.getByTestId("scroll-to-bottom")).toHaveCount(0);
    await expect(panel).toContainText("Snapshot lookup_e2e_agent_snapshot");
    await expect(panel).toContainText("Lookup evidence workbench");
    await expect(panel).toContainText("evidence-parking-e2e");
    await expect(panel).toContainText("Official zoning map");
    await expect(panel).toContainText("max_units=1");
    await expect(panel).toContainText("human review");
    await expect(panel).toContainText("Confirm adopted parking table.");

    const releaseGatePanel = page.getByTestId("lookup-release-gate-panel");
    await expect(releaseGatePanel).toContainText("missing_eval_history");
    await releaseGatePanel.getByTestId("lookup-release-gate-run").click();
    await expect(releaseGatePanel).toContainText("Recorded 1 golden case eval.");
    await expect(releaseGatePanel).toContainText("Latest eval passed: eval-e2e-pass.");
    await releaseGatePanel.evaluate((element) =>
      element.scrollIntoView({ block: "center", inline: "nearest" }),
    );
    await page.screenshot({ path: testInfo.outputPath("agent-run-panel-ready.png") });

    for (const visualViewport of visualViewports) {
      await page.setViewportSize({
        width: visualViewport.width,
        height: visualViewport.height,
      });
      const chatHistoryBox = await page.getByText("Chat History").boundingBox();
      if (
        chatHistoryBox &&
        chatHistoryBox.x < visualViewport.width &&
        chatHistoryBox.x + chatHistoryBox.width > 0
      ) {
        await page.keyboard.press("Control+B");
        await expect
          .poll(async () => {
            const box = await page.getByText("Chat History").boundingBox();
            return !box || box.x >= visualViewport.width || box.x + box.width <= 0;
          })
          .toBeTruthy();
      }
      await releaseGatePanel.evaluate((element) =>
        element.scrollIntoView({ block: "center", inline: "nearest" }),
      );
      await expect(releaseGatePanel).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`lookup-release-gate-report-${visualViewport.name}.png`),
      });
    }

    await page.setViewportSize({ width: 1280, height: 720 });
    await panel.scrollIntoViewIfNeeded();

    await page.getByTestId("agent-run-start").click();

    await expect(panel).toContainText("Release gate clear");
    await expect(panel).toContainText("Replay trace");
    await expect(panel).toContainText("Replay ready");
    await expect(panel).toContainText("report_e2e_agent");
    await expect(panel).toContainText("Evidence packets");
    await expect(panel).toContainText("2 packets");
    await expect(panel).toContainText("Source retrievals");
    await expect(panel).toContainText("2 retrievals");
    await expect(panel).toContainText("Recorded zoning map packet");
    await expect(panel).toContainText("City of Miramar");
    await expect(panel).toContainText("raw://zoning/evidence-zoning-e2e");
    await expect(panel).toContainText("official_zoning_map");
    await expect(panel).toContainText("zoning-map-v2");
    await expect(panel).toContainText("schema_stable");
    await expect(panel).toContainText("Report claims");
    await expect(panel).toContainText("Deterministic Calculations");
    await expect(panel).toContainText(
      "Deterministic calculation output from underwriting_analyst: max_units=1.",
    );
    const reportClaims = page.getByTestId("agent-run-report-claims");
    await reportClaims.evaluate((element) =>
      element.scrollIntoView({ block: "center", inline: "nearest" }),
    );
    await expect(reportClaims).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("agent-run-report-claims.png") });
    const opportunities = page.getByTestId("agent-run-opportunities");
    await opportunities.evaluate((element) =>
      element.scrollIntoView({ block: "center", inline: "nearest" }),
    );
    await expect(opportunities).toBeVisible();
    await expect(opportunities).toContainText("Opportunity hypotheses");
    await expect(opportunities).toContainText("opportunity.by_right_capacity");
    await expect(opportunities).toContainText("hypothesis");
    await expect(opportunities).toContainText("max_units=1");
    await page.screenshot({ path: testInfo.outputPath("agent-run-opportunities.png") });
    await expect(panel).toContainText("Artifact assumptions");
    await expect(panel).toContainText("requires_human_review");
    await expect(panel).toContainText("agent_run.open_question");
    await expect(panel).toContainText("Evidence");
    await expect(panel).toContainText("Trace");
    await expect(panel).toContainText("Assumptions");
    const replayTrace = panel.getByText("Replay trace");
    await replayTrace.scrollIntoViewIfNeeded();
    await expect(replayTrace).toBeVisible();
    await replayTrace.evaluate((element) =>
      element.scrollIntoView({ block: "center", inline: "nearest" }),
    );
    await expect
      .poll(async () => {
        const box = await panel.boundingBox();
        return box?.y ?? 999;
      })
      .toBeLessThan(120);
    await page.screenshot({ path: testInfo.outputPath("agent-run-panel-evaluated.png") });

    for (const visualViewport of visualViewports) {
      await page.setViewportSize({
        width: visualViewport.width,
        height: visualViewport.height,
      });
      const chatHistoryBox = await page.getByText("Chat History").boundingBox();
      if (
        chatHistoryBox &&
        chatHistoryBox.x < visualViewport.width &&
        chatHistoryBox.x + chatHistoryBox.width > 0
      ) {
        await page.keyboard.press("Control+B");
        await expect
          .poll(async () => {
            const box = await page.getByText("Chat History").boundingBox();
            return !box || box.x >= visualViewport.width || box.x + box.width <= 0;
          })
          .toBeTruthy();
      }
      await replayTrace.scrollIntoViewIfNeeded();
      await replayTrace.evaluate((element) =>
        element.scrollIntoView({ block: "center", inline: "nearest" }),
      );
      await expect(replayTrace).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`agent-run-panel-${visualViewport.name}.png`),
      });
    }
  });
});
